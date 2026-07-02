from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from craftsman.config import settings
from craftsman.orchestrator.policy_checks import check_release_compliance_metadata
from craftsman.publisher.android_build import build_release_aab, write_build_manifest
from craftsman.publisher.android_signing import cleanup_keystore_properties, write_keystore_properties
from craftsman.publisher.android_version import bump_version_for_release
from craftsman.publisher.handoff import (
    application_id,
    platform_target,
    resolve_icon_path,
    resolve_metadata_dir,
    resolve_project_dir,
    resolve_screenshot_paths,
    resolve_workspace_dir,
)
from craftsman.publisher.models import PublisherPhase, PublisherStatus
from craftsman.publisher.play_client import build_android_publisher_service, service_account_info
from craftsman.publisher.play_store import upload_to_play
from craftsman.publisher.preflight import run_release_preflight
from craftsman.schema_validate import validate_release_handoff

logger = logging.getLogger(__name__)


def run_android_release(
    handoff: dict[str, Any],
    *,
    release_id: str,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """
    Agent C orchestrator: validate → sign → version bump → build → upload.

    Returns a publisher result dict suitable for API responses and audit logs.
    """
    effective_dry_run = settings.publisher_dry_run if dry_run is None else dry_run
    phases: list[dict[str, str]] = []

    def _phase(name: PublisherPhase, detail: str) -> None:
        phases.append({"phase": name.value, "detail": detail})
        logger.info("agent_c phase=%s detail=%s release_id=%s", name.value, detail, release_id)

    _phase(PublisherPhase.VALIDATE, "validate release_handoff")
    if platform_target(handoff) != "android":
        return _failure(release_id, phases, ["platform target is not android"], handoff)

    quality_blocker = _quality_blocker(handoff)
    if quality_blocker:
        return _failure(
            release_id,
            phases,
            [quality_blocker["operator_action"]],
            handoff,
        )

    schema_errors = validate_release_handoff(handoff)
    if schema_errors:
        return _failure(release_id, phases, [f"schema: {e}" for e in schema_errors[:5]], handoff)

    policy = check_release_compliance_metadata(handoff)
    if not policy["passed"]:
        return _failure(release_id, phases, [f"policy: {i}" for i in policy["issues"]], handoff)

    preflight = run_release_preflight(handoff, dry_run=effective_dry_run)
    if not preflight["ok"]:
        return _failure(
            release_id,
            phases,
            [preflight["message"]],
            handoff,
            failure_class=preflight.get("failure_class"),
            operator_action=preflight.get("operator_action"),
            preflight=preflight,
        )

    project_dir = resolve_project_dir(handoff)
    workspace = resolve_workspace_dir(handoff)
    if project_dir is None or workspace is None:
        return _failure(release_id, phases, ["cannot resolve project/workspace from handoff"], handoff)

    package = application_id(handoff) or settings.google_play_package_name
    if not package:
        return _failure(release_id, phases, ["application_id / package_name missing"], handoff)

    metadata_dir = resolve_metadata_dir(handoff)
    icon_path = resolve_icon_path(handoff)
    screenshot_paths = resolve_screenshot_paths(handoff)

    from craftsman.publisher.play_console_sheet import generate_play_console_sheet

    setup_sheet = generate_play_console_sheet(
        handoff=handoff,
        workspace=workspace,
        icon_path=str(icon_path) if icon_path else None,
        screenshot_paths=[str(p) for p in screenshot_paths] if screenshot_paths else None,
    )
    _phase(PublisherPhase.VALIDATE, "play console setup sheet generated")

    _phase(PublisherPhase.SIGN, "configure android signing")
    signing_ok, signing_msg = write_keystore_properties(project_dir)

    play_service = None
    if not effective_dry_run and service_account_info() is not None:
        try:
            play_service = build_android_publisher_service()
        except RuntimeError as exc:
            return _failure(release_id, phases, [str(exc)], handoff)

    version_detail = "version bump skipped (dry-run)"
    if not effective_dry_run:
        _phase(PublisherPhase.BUILD, "bump versionCode for Play")
        _, _, version_detail = bump_version_for_release(
            project_dir,
            package_name=package,
            track=settings.android_release_track,
            dry_run=False,
            service=play_service,
        )
        phases[-1]["detail"] = version_detail

    release_track = "internal"
    _phase(PublisherPhase.BUILD, "build release AAB for internal testing")
    _phase(PublisherPhase.UPLOAD, f"upload to track {release_track}")
    upload, aab_path = _upload_with_healing(
        project_dir=project_dir,
        package_name=package,
        metadata_dir=metadata_dir,
        icon_path=icon_path,
        screenshot_paths=screenshot_paths,
        effective_dry_run=effective_dry_run,
        release_track=release_track,
        phases=phases,
        release_id=release_id,
        handoff=handoff,
        max_retries=3,
    )
    if not upload.ok:
        return _failure(
            release_id,
            phases,
            [upload.message],
            handoff,
            upload={
                "track": upload.track,
                "message": upload.message,
                "dry_run": upload.dry_run,
                "store_response": upload.store_response,
            },
            release_bundle={"aab_path": aab_path} if aab_path else None,
        )

    # ---- 自动推送到 production（触发 Google 人工审核） ----
    production_result: dict[str, Any] = {}
    if False and settings.auto_promote_to_production and not effective_dry_run and upload.track != "production":
        _phase(PublisherPhase.UPLOAD, "promote to production track (Google review)")
        promote = _upload_to_track_only(
            aab_path=Path(aab_path),
            package_name=package,
            track="production",
            service=play_service,
        )
        production_result = {
            "promoted_to_production": promote.ok,
            "production_track": "production",
            "message": promote.message,
            "store_response": promote.store_response,
        }
        if promote.ok:
            _phase(PublisherPhase.COMPLETE, "submitted to production (pending Google review)")
        else:
            _phase(PublisherPhase.UPLOAD, f"production promotion failed: {promote.message}")
            # 不阻塞：internal 已经成功，production 推送失败记录但不中断
    elif upload.track == "production":
        production_result = {
            "promoted_to_production": True,
            "production_track": "production",
            "message": "published directly to production",
        }

    write_build_manifest(
        workspace,
        {
            "release_id": release_id,
            "aab_path": aab_path,
            "signing": signing_msg,
            "dry_run": upload.dry_run,
            "version": version_detail,
            "package_name": package,
        },
    )

    status = PublisherStatus.DRY_RUN_COMPLETE if upload.dry_run else PublisherStatus.INTERNAL_SUBMITTED
    _phase(PublisherPhase.COMPLETE, status.value)

    bundle = dict(handoff.get("release_bundle") or {})
    bundle["aab_path"] = aab_path

    return {
        "release_id": release_id,
        "agent_c_status": status.value,
        "platform_target": "android",
        "phase": PublisherPhase.COMPLETE.value,
        "track": release_track,
        "failure_class": None,
        "operator_action": "内部测试轨道已提交，可在 Play Console 查看。" if not upload.dry_run else "dry-run 已完成；配置服务账号后可真实上传 internal track。",
        "phases": phases,
        "release_bundle": bundle,
        "upload": {
            "track": upload.track,
            "message": upload.message,
            "dry_run": upload.dry_run,
            "store_response": upload.store_response,
        },
        "signing": {"configured": signing_ok, "message": signing_msg},
        "version": version_detail,
        "dry_run": upload.dry_run,
        "production": production_result or None,
        "release_handoff": {**handoff, "release_bundle": bundle},
        "play_console_setup_path": setup_sheet.get("path"),
        "setup_sheet": setup_sheet.get("text"),
    }



def classify_play_failure(message: str) -> dict[str, str]:
    text = (message or "").lower()
    if "quality" in text or "质量" in text or "质量分" in text:
        return {"failure_class": "quality_gate_blocked", "operator_action": "App 质量分未达到 75，需继续修复或人工确认后再发布。"}
    if "not found" in text or "package" in text and "created" in text:
        return {"failure_class": "package_not_precreated", "operator_action": "请先在 Play Console 预创建这个包名，并确认包名池配置正确。"}
    if "permission" in text or "unauthorized" in text or "forbidden" in text or "401" in text or "403" in text:
        return {"failure_class": "service_account_permission", "operator_action": "请检查 Google Play service account 权限和 play-sa.json 配置。"}
    if "versioncode" in text or "already been used" in text:
        return {"failure_class": "version_code_conflict", "operator_action": "请重试发布，系统会尝试提升 versionCode。"}
    if "sign" in text or "keystore" in text:
        return {"failure_class": "signing_config", "operator_action": "请检查 release.jks、密码和签名配置。"}
    if "metadata" in text or "listing" in text or "privacy" in text:
        return {"failure_class": "metadata_incomplete", "operator_action": "请补齐商店描述、截图、图标和隐私政策 URL。"}
    if "track" in text or "internal" in text:
        return {"failure_class": "internal_track_unavailable", "operator_action": "请在 Play Console 检查内部测试轨道是否可用。"}
    if "timeout" in text or "tempor" in text or "rate" in text:
        return {"failure_class": "play_api_transient", "operator_action": "Google Play API 临时失败，请稍后重试。"}
    return {"failure_class": "play_api_error", "operator_action": "请查看发布详情中的 Google Play 错误信息。"}


def _quality_blocker(handoff: dict[str, Any]) -> dict[str, Any] | None:
    report = handoff.get("quality_report") if isinstance(handoff.get("quality_report"), dict) else {}
    score = handoff.get("quality_score")
    if score is None:
        score = report.get("quality_score")
    release_ready = handoff.get("release_ready")
    if release_ready is None:
        release_ready = report.get("release_ready")
    if score is None:
        return None
    try:
        score_int = int(score)
    except (TypeError, ValueError):
        score_int = 0
    if bool(release_ready) and score_int >= 75:
        return None
    return {
        "quality_score": score_int,
        "release_ready": bool(release_ready),
        "failure_classes": report.get("failure_classes") or [],
        "operator_action": "App quality score is below 75; improve Agent B output before submitting to Google Play internal track.",
    }

def _failure(
    release_id: str,
    phases: list[dict[str, str]],
    reasons: list[str],
    handoff: dict[str, Any],
    *,
    log: str = "",
    failure_class: str | None = None,
    operator_action: str | None = None,
    preflight: dict[str, Any] | None = None,
    upload: dict[str, Any] | None = None,
    release_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message = "; ".join(reasons[:3])
    classification = classify_play_failure(message or log)
    phases.append({"phase": PublisherPhase.FAILED.value, "detail": message})
    return {
        "release_id": release_id,
        "agent_c_status": PublisherStatus.FAILED.value,
        "platform_target": platform_target(handoff),
        "phase": PublisherPhase.FAILED.value,
        "track": "internal",
        "failure_class": failure_class or classification["failure_class"],
        "operator_action": operator_action or classification["operator_action"],
        "phases": phases,
        "reasons": reasons,
        "build_log": log,
        "release_handoff": handoff,
        "preflight": preflight,
        "upload": upload,
        "release_bundle": release_bundle,
    }

def _upload_with_healing(
    *,
    project_dir: Path,
    package_name: str,
    metadata_dir: Path | None,
    icon_path: Path | None,
    screenshot_paths: list[Path] | None,
    effective_dry_run: bool,
    release_track: str,
    phases: list[dict[str, str]],
    release_id: str,
    handoff: dict[str, Any],
    max_retries: int = 3,
):
    """Upload to Play with self-healing retry for common recoverable errors.

    Returns (upload_result, aab_path_str).
    """
    import re

    for attempt in range(max_retries + 1):
        if attempt > 0:
            logger.warning(
                "upload self-heal attempt %d/%d release_id=%s",
                attempt, max_retries, release_id,
            )

        # Build (or rebuild) AAB
        from craftsman.publisher.android_build import build_release_aab
        from craftsman.publisher.android_signing import write_keystore_properties, cleanup_keystore_properties

        signing_ok, _ = write_keystore_properties(project_dir)
        build = build_release_aab(project_dir, dry_run=effective_dry_run)
        if signing_ok:
            cleanup_keystore_properties(project_dir)

        if not build.ok or not build.aab_path:
            phases.append({"phase": PublisherPhase.BUILD.value, "detail": f"build failed (attempt {attempt + 1})"})
            if attempt < max_retries:
                continue
            from craftsman.publisher.models import ReleaseUploadResult
            return ReleaseUploadResult(ok=False, track=release_track, message="build failed after retries",
                                       store_response={"build_log": build.log}), ""

        if attempt > 0:
            phases.append({"phase": PublisherPhase.BUILD.value, "detail": f"rebuild (attempt {attempt + 1})"})

        # Upload
        upload = upload_to_play(
            aab_path=Path(build.aab_path),
            package_name=package_name,
            dry_run=effective_dry_run,
            metadata_dir=metadata_dir,
            icon_path=icon_path,
            screenshot_paths=screenshot_paths,
            sync_store_assets=attempt == 0,
        )

        if upload.ok:
            return upload, build.aab_path

        msg = upload.message.lower()
        failed_stage = str((upload.store_response or {}).get("failed_stage") or "").lower()
        if (
            failed_stage == "commit"
            and attempt == 0
            and (upload.store_response or {}).get("images", {}).get("uploaded")
        ):
            phases.append({
                "phase": PublisherPhase.UPLOAD.value,
                "detail": "commit failed after store asset sync; retrying internal AAB without listing/images",
            })
            _bump_gradle_property(project_dir, "versionCode", _read_gradle_int(project_dir, "versionCode") + 1)
            continue

        # --- Self-healing rules ---

        # Target SDK too low
        if "target sdk" in msg and "too low" in msg:
            target = max(_highest_installed_android_platform(project_dir), 36)
            logger.info("healing: bumping targetSdk to %d", target)
            _bump_gradle_property(project_dir, "targetSdk", target)
            _bump_gradle_property(project_dir, "compileSdk", target)
            _bump_gradle_property(project_dir, "versionCode", _read_gradle_int(project_dir, "versionCode") + 1)
            continue

        # Version code already used
        if "already been used" in msg or "versioncode conflict" in msg:
            current = _read_gradle_int(project_dir, "versionCode")
            new_vc = current + 1
            logger.info("healing: bumping versionCode %d -> %d", current, new_vc)
            _bump_gradle_property(project_dir, "versionCode", new_vc)
            continue

        # Bundle not signed
        if "must be signed" in msg or "sign" in msg:
            logger.info("healing: re-configuring signing")
            from craftsman.publisher.android_signing import write_keystore_properties as _wks
            _wks(project_dir)
            continue

        # Unrecoverable
        return upload, build.aab_path

    # Exhausted retries
    from craftsman.publisher.models import ReleaseUploadResult
    return ReleaseUploadResult(ok=False, track=release_track,
                               message=f"upload failed after {max_retries + 1} attempts"), ""


def _read_gradle_int(project_dir: Path, key: str) -> int:
    import re
    gf = project_dir / "app" / "build.gradle.kts"
    if not gf.is_file():
        return 1
    m = re.search(rf"{key}\s*=\s*(\d+)", gf.read_text(encoding="utf-8"))
    return int(m.group(1)) if m else 1


def _highest_installed_android_platform(project_dir: Path) -> int:
    import os
    import re

    candidates: list[Path] = []
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if android_home:
        candidates.append(Path(android_home) / "platforms")
    candidates.append(Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platforms")
    candidates.append(project_dir.parent / "android-sdk" / "platforms")
    versions: list[int] = []
    for root in candidates:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            m = re.match(r"android-(\d+)", child.name)
            if m:
                versions.append(int(m.group(1)))
    return max(versions or [36])


def _bump_gradle_property(project_dir: Path, key: str, value: int) -> None:
    import re
    gf = project_dir / "app" / "build.gradle.kts"
    if not gf.is_file():
        return
    text = gf.read_text(encoding="utf-8")
    text = re.sub(rf"{key}\s*=\s*\d+", f"{key} = {value}", text)
    gf.write_text(text, encoding="utf-8")


def _upload_to_track_only(
    *,
    aab_path: Path,
    package_name: str,
    track: str,
    service,
):
    """Upload an existing AAB to a specific track only (no listing/images sync). Used for
    promoting from internal/alpha/beta to production."""
    import logging

    from craftsman.publisher.play_client import map_play_api_error
    from craftsman.publisher.models import ReleaseUploadResult

    _logger = logging.getLogger(__name__)

    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return ReleaseUploadResult(ok=False, track=track, message="google-api-python-client not installed")

    try:
        edit = service.edits().insert(packageName=package_name, body={}).execute()
        edit_id = str(edit["id"])

        media = MediaFileUpload(str(aab_path), mimetype="application/octet-stream", resumable=True)
        bundle = (
            service.edits()
            .bundles()
            .upload(packageName=package_name, editId=edit_id, media_body=media)
            .execute()
        )
        version_code = str(bundle.get("versionCode") or "")

        if not version_code:
            service.edits().delete(packageName=package_name, editId=edit_id).execute()
            return ReleaseUploadResult(ok=False, track=track, message="bundle upload returned no versionCode")

        track_body = {
            "releases": [
                {"status": "completed", "versionCodes": [version_code]}
            ]
        }
        service.edits().tracks().update(
            packageName=package_name,
            editId=edit_id,
            track=track,
            body=track_body,
        ).execute()

        commit = service.edits().commit(packageName=package_name, editId=edit_id).execute()

        _logger.info("promoted to %s track: edit=%s vc=%s", track, edit_id, version_code)
        return ReleaseUploadResult(
            ok=True,
            track=track,
            message=f"submitted to {track} track (versionCode={version_code}, pending Google review)",
            dry_run=False,
            store_response={"edit_id": edit_id, "versionCode": version_code, "commit": commit},
        )
    except Exception as exc:
        mapped = map_play_api_error(exc)
        _logger.warning("promotion to %s failed: %s", track, mapped)
        return ReleaseUploadResult(ok=False, track=track, message=mapped, store_response={"error": mapped})

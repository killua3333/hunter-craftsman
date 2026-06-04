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

    schema_errors = validate_release_handoff(handoff)
    if schema_errors:
        return _failure(release_id, phases, [f"schema: {e}" for e in schema_errors[:5]], handoff)

    policy = check_release_compliance_metadata(handoff)
    if not policy["passed"]:
        return _failure(release_id, phases, [f"policy: {i}" for i in policy["issues"]], handoff)

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

    _phase(PublisherPhase.BUILD, "gradle bundleRelease")
    build = build_release_aab(project_dir, dry_run=effective_dry_run)
    if signing_ok:
        cleanup_keystore_properties(project_dir)
    if not build.ok or not build.aab_path:
        return _failure(release_id, phases, build.reasons or ["build failed"], handoff, log=build.log)

    write_build_manifest(
        workspace,
        {
            "release_id": release_id,
            "aab_path": build.aab_path,
            "signing": signing_msg,
            "dry_run": build.dry_run,
            "version": version_detail,
            "package_name": package,
        },
    )

    _phase(PublisherPhase.UPLOAD, f"upload to track {settings.android_release_track}")
    upload = upload_to_play(
        aab_path=Path(build.aab_path),
        package_name=package,
        dry_run=effective_dry_run or build.dry_run,
        metadata_dir=metadata_dir,
        icon_path=icon_path,
        screenshot_paths=screenshot_paths,
    )
    if not upload.ok:
        return _failure(release_id, phases, [upload.message], handoff)

    status = PublisherStatus.DRY_RUN_COMPLETE if upload.dry_run else PublisherStatus.SUBMITTED
    _phase(PublisherPhase.COMPLETE, status.value)

    bundle = dict(handoff.get("release_bundle") or {})
    bundle["aab_path"] = build.aab_path

    return {
        "release_id": release_id,
        "agent_c_status": status.value,
        "platform_target": "android",
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
        "release_handoff": {**handoff, "release_bundle": bundle},
        "play_console_setup_path": setup_sheet.get("path"),
        "setup_sheet": setup_sheet.get("text"),
    }


def _failure(
    release_id: str,
    phases: list[dict[str, str]],
    reasons: list[str],
    handoff: dict[str, Any],
    *,
    log: str = "",
) -> dict[str, Any]:
    phases.append({"phase": PublisherPhase.FAILED.value, "detail": "; ".join(reasons[:3])})
    return {
        "release_id": release_id,
        "agent_c_status": PublisherStatus.FAILED.value,
        "platform_target": platform_target(handoff),
        "phases": phases,
        "reasons": reasons,
        "build_log": log,
        "release_handoff": handoff,
    }

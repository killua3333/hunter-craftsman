from __future__ import annotations

from pathlib import Path
from typing import Any

from craftsman.config import settings
from craftsman.publisher.android_signing import signing_configured
from craftsman.publisher.handoff import (
    application_id,
    resolve_icon_path,
    resolve_metadata_dir,
    resolve_project_dir,
    resolve_screenshot_paths,
    resolve_workspace_dir,
)
from craftsman.publisher.play_client import (
    build_android_publisher_service,
    map_play_api_error,
    service_account_info,
)
from craftsman.secrets import resolve_secret_path, resolve_secret_value


def run_release_preflight(
    handoff: dict[str, Any],
    *,
    dry_run: bool,
    service: Any | None = None,
) -> dict[str, Any]:
    """Validate local artifacts and live Google Play permissions before upload."""
    checks: list[dict[str, Any]] = []
    package_name = application_id(handoff) or settings.google_play_package_name
    project_dir = resolve_project_dir(handoff)
    workspace = resolve_workspace_dir(handoff)
    metadata_dir = resolve_metadata_dir(handoff)
    icon_path = resolve_icon_path(handoff)
    screenshots = resolve_screenshot_paths(handoff)

    _check(checks, "package_name", bool(package_name), "包名已解析", "缺少 Android applicationId / package name")
    _check(checks, "project_dir", bool(project_dir and project_dir.is_dir()), "工程目录存在", "无法解析工程目录")
    _check(checks, "workspace", bool(workspace and workspace.is_dir()), "workspace 存在", "无法解析 workspace")
    _check(checks, "metadata", bool(metadata_dir and metadata_dir.is_dir()), "商店 metadata 存在", "缺少 Play metadata 目录")
    _check(checks, "icon", bool(icon_path and icon_path.is_file()), "图标存在", "缺少商店图标")
    _check(checks, "screenshots", bool(screenshots), "截图存在", "缺少至少一张商店截图")

    if project_dir is not None:
        _check(
            checks,
            "gradle_file",
            (project_dir / "app" / "build.gradle.kts").is_file(),
            "Gradle app 脚本存在",
            "缺少 app/build.gradle.kts",
        )

    if dry_run:
        return _finish(checks, package_name=package_name, dry_run=True)

    signing = _live_signing_status()
    _check(
        checks,
        "signing",
        signing["ok"],
        signing["message"],
        signing["message"],
        failure_class="signing_config",
        operator_action="请配置 Android release signing，并确认 keystore 文件和密码可用。",
    )

    account_ok = service is not None or service_account_info() is not None
    _check(
        checks,
        "service_account",
        account_ok,
        "Google Play service account 已配置",
        "缺少 Google Play service account",
        failure_class="service_account_permission",
        operator_action="请配置 GOOGLE_PLAY_SERVICE_ACCOUNT_FILE 或 GOOGLE_PLAY_SERVICE_ACCOUNT_JSON。",
    )

    if package_name and account_ok:
        checks.extend(
            _check_play_edit_access(
                package_name=str(package_name),
                track=settings.android_release_track or "internal",
                service=service,
            )["checks"]
        )

    return _finish(checks, package_name=package_name, dry_run=False)


def _live_signing_status() -> dict[str, Any]:
    store_path = resolve_secret_path("ANDROID_KEYSTORE_PATH", settings.android_keystore_path)
    if not signing_configured() or not store_path:
        return {"ok": False, "message": "release signing secrets not configured"}
    if not Path(store_path).is_file():
        return {"ok": False, "message": f"keystore file not found: {store_path}"}
    missing = [
        key
        for key, value in {
            "ANDROID_KEYSTORE_PASSWORD": resolve_secret_value("ANDROID_KEYSTORE_PASSWORD", settings.android_keystore_password),
            "ANDROID_KEY_ALIAS": resolve_secret_value("ANDROID_KEY_ALIAS", settings.android_key_alias),
            "ANDROID_KEY_PASSWORD": resolve_secret_value("ANDROID_KEY_PASSWORD", settings.android_key_password),
        }.items()
        if not value
    ]
    if missing:
        return {"ok": False, "message": "missing signing secrets: " + ", ".join(missing)}
    return {"ok": True, "message": "release signing configured"}


def _check_play_edit_access(
    *,
    package_name: str,
    track: str,
    service: Any | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        live_service = service or build_android_publisher_service()
        edit = live_service.edits().insert(packageName=package_name, body={}).execute()
        edit_id = str(edit["id"])
        _check(checks, "play_edit", True, "Play edit 可创建，包名和基础权限可用", "")
        try:
            track_payload = live_service.edits().tracks().get(
                packageName=package_name,
                editId=edit_id,
                track=track,
            ).execute()
            _check(checks, "play_track", True, f"Play {track} track 可读取", "")
            try:
                live_service.edits().tracks().update(
                    packageName=package_name,
                    editId=edit_id,
                    track=track,
                    body={"track": track, "releases": track_payload.get("releases") or []},
                ).execute()
                _check(checks, "play_track_write", True, f"Play {track} track 可写入", "")
            except Exception as exc:
                mapped = map_play_api_error(exc)
                _check(
                    checks,
                    "play_track_write",
                    False,
                    "",
                    mapped,
                    failure_class=_failure_class_from_play_message(mapped),
                    operator_action=_operator_action_from_play_message(mapped),
                )
        except Exception as exc:
            mapped = map_play_api_error(exc)
            _check(
                checks,
                "play_track",
                False,
                "",
                mapped,
                failure_class=_failure_class_from_play_message(mapped),
                operator_action=_operator_action_from_play_message(mapped),
            )
        finally:
            try:
                live_service.edits().delete(packageName=package_name, editId=edit_id).execute()
            except Exception:
                pass
    except Exception as exc:
        mapped = map_play_api_error(exc)
        _check(
            checks,
            "play_edit",
            False,
            "",
            mapped,
            failure_class=_failure_class_from_play_message(mapped),
            operator_action=_operator_action_from_play_message(mapped),
        )
    return {"checks": checks}


def _check(
    checks: list[dict[str, Any]],
    name: str,
    ok: bool,
    ok_message: str,
    fail_message: str,
    *,
    failure_class: str | None = None,
    operator_action: str | None = None,
) -> None:
    checks.append(
        {
            "name": name,
            "ok": bool(ok),
            "message": ok_message if ok else fail_message,
            "failure_class": None if ok else failure_class,
            "operator_action": None if ok else operator_action,
        }
    )


def _finish(checks: list[dict[str, Any]], *, package_name: str | None, dry_run: bool) -> dict[str, Any]:
    failed = [item for item in checks if not item.get("ok")]
    first = failed[0] if failed else {}
    failure_class = first.get("failure_class") or _failure_class_for_check(str(first.get("name") or ""))
    operator_action = first.get("operator_action") or _operator_action_for_check(str(first.get("name") or ""))
    return {
        "ok": not failed,
        "dry_run": dry_run,
        "package_name": package_name,
        "track": settings.android_release_track or "internal",
        "checks": checks,
        "failure_class": None if not failed else failure_class,
        "operator_action": "发布前检查通过。" if not failed else operator_action,
        "message": "发布前检查通过。" if not failed else str(first.get("message") or "发布前检查失败"),
    }


def _failure_class_for_check(name: str) -> str:
    if name == "package_name":
        return "package_name_missing"
    if name in {"project_dir", "workspace", "gradle_file"}:
        return "release_handoff_incomplete"
    if name in {"metadata", "icon", "screenshots"}:
        return "metadata_incomplete"
    if name == "signing":
        return "signing_config"
    if name == "service_account":
        return "service_account_permission"
    return "preflight_failed"


def _operator_action_for_check(name: str) -> str:
    if name == "package_name":
        return "请确认 Agent B 写入了 app.application_id / bundle_id。"
    if name in {"project_dir", "workspace", "gradle_file"}:
        return "请重新运行 Agent B，确保工程和 release_handoff 完整。"
    if name in {"metadata", "icon", "screenshots"}:
        return "请补齐商店 metadata、图标和截图后再发布。"
    if name == "signing":
        return "请配置 Android release signing 后再真实上传。"
    if name == "service_account":
        return "请配置 Google Play service account，并授予目标应用发布权限。"
    return "请查看发布前检查详情并修复失败项。"


def _failure_class_from_play_message(message: str) -> str:
    lower = message.lower()
    if "not found" in lower or "not registered" in lower:
        return "package_not_precreated"
    if "permission" in lower or "forbidden" in lower or "denied" in lower or "401" in lower or "403" in lower:
        return "service_account_permission"
    if "track" in lower or "internal" in lower:
        return "internal_track_unavailable"
    return "play_api_error"


def _operator_action_from_play_message(message: str) -> str:
    failure_class = _failure_class_from_play_message(message)
    if failure_class == "package_not_precreated":
        return "请先在 Play Console 预创建这个包名，并确认包名池只包含已创建应用。"
    if failure_class == "service_account_permission":
        return "请在 Play Console 给 service account 授予目标应用的 Release manager 权限。"
    if failure_class == "internal_track_unavailable":
        return "请检查 Play Console 内部测试轨道是否已启用。"
    return "请查看 Google Play API 返回信息后重试。"

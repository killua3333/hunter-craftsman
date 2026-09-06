from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEVICE_SCREENSHOT_DIR = Path("app/build/reports/device-acceptance")


def build_android_device_acceptance_report(
    *,
    project_dir: Path,
    build_verified: bool,
    smoke_ok: bool,
    smoke_skipped: bool,
    smoke_reason: str,
    acceptance_actions: list[str],
) -> dict[str, Any]:
    screenshots = _device_screenshots(project_dir)
    launch_verified = bool(build_verified and smoke_ok and not smoke_skipped)
    if not build_verified:
        status = "failed"
        operator_message = "Android 工程尚未通过原生编译。"
    elif smoke_skipped:
        status = "unavailable"
        operator_message = "原生工程已编译，但当前环境没有完成设备启动检查。"
    elif not smoke_ok:
        status = "failed"
        operator_message = "App 在设备启动检查中失败，需要修复后重新测试。"
    else:
        status = "launch_verified"
        operator_message = "App 已在测试设备启动并完成随机操作检查；核心业务流程仍需专项验收。"

    return {
        "schema_version": 1,
        "platform": "android",
        "status": status,
        "build_verified": bool(build_verified),
        "launch_verified": launch_verified,
        "random_smoke_verified": launch_verified,
        "core_flow_verified": False,
        "persistence_verified": False,
        "planned_acceptance_actions": list(acceptance_actions),
        "executed_acceptance_actions": [
            "安装 APK",
            "启动 App",
            "执行随机界面操作并检查崩溃",
            "强制停止后重新启动 App",
        ] if launch_verified else [],
        "device_screenshots": screenshots,
        "screenshot_source": "android_emulator" if screenshots else None,
        "smoke_reason": smoke_reason or None,
        "operator_message": operator_message,
    }


def write_device_acceptance_report(workspace: Path, report: dict[str, Any]) -> Path:
    path = workspace / "device_acceptance_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def unavailable_android_device_report(
    *,
    build_verified: bool,
    reason: str,
    acceptance_actions: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "platform": "android",
        "status": "unavailable",
        "build_verified": bool(build_verified),
        "launch_verified": False,
        "random_smoke_verified": False,
        "core_flow_verified": False,
        "persistence_verified": False,
        "planned_acceptance_actions": list(acceptance_actions),
        "executed_acceptance_actions": [],
        "device_screenshots": [],
        "screenshot_source": None,
        "smoke_reason": reason,
        "operator_message": "当前环境没有完成 Android 设备启动检查。",
    }


def _device_screenshots(project_dir: Path) -> list[str]:
    root = project_dir / DEVICE_SCREENSHOT_DIR
    return [str(path) for path in sorted(root.glob("*.png")) if path.is_file() and path.stat().st_size > 0]

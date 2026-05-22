from __future__ import annotations

import platform
import sys
from pathlib import Path

from craftsman.config import settings
from craftsman.tools.shell import run_cmd


def is_macos_with_xcode() -> bool:
    if settings.skip_xcodebuild:
        return False
    if platform.system() != "Darwin":
        return False
    r = run_cmd(["which", "xcodebuild"], timeout=10.0)
    return r.exit_code == 0


def simulator_build(project_dir: Path, scheme: str) -> tuple[int, str]:
    destination = f"platform=iOS Simulator,name={settings.simulator_name}"
    cmd = [
        "xcodebuild",
        "-project",
        str(project_dir / f"{scheme}.xcodeproj"),
        "-scheme",
        scheme,
        "-destination",
        destination,
        "-configuration",
        "Debug",
        "build",
    ]
    result = run_cmd(cmd, cwd=str(project_dir), timeout=900.0)
    log = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.timed_out:
        log += "\n[xcodebuild timed out]"
    return result.exit_code, log


def platform_note() -> str:
    return f"system={platform.system()} python={sys.version.split()[0]}"

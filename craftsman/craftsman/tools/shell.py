from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import PurePath
from typing import Mapping


@dataclass
class CmdResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


ALLOWED_PREFIXES = (
    "xcodebuild",
    "xcrun",
    "fastlane",
    "python",
    "git",
    "which",
    "swift",
    "gradle",
    "gradlew",
    "gradlew.bat",
)


def run_cmd(
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = 600.0,
) -> CmdResult:
    if not cmd:
        raise ValueError("empty command")
    exe = cmd[0].lower()
    exe_name = PurePath(exe).name
    if not any(exe == p or exe_name == p or exe.endswith("/" + p) or exe.endswith("\\" + p) for p in ALLOWED_PREFIXES):
        raise PermissionError(f"command not allowed: {cmd[0]}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=dict(env) if env else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CmdResult(proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired as exc:
        return CmdResult(
            -1,
            exc.stdout or "",
            (exc.stderr or "") + "\n[timeout]",
            timed_out=True,
        )

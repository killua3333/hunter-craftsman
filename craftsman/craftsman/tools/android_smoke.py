"""Android 模拟器冒烟测试（Docker builder 内 monkey）。"""

from __future__ import annotations

from dataclasses import dataclass

from craftsman.config import settings
from craftsman.runtime.docker_android import is_docker_available, run_smoke_in_container


@dataclass
class SmokeResult:
    ok: bool
    skipped: bool
    reason: str
    log: str


def should_run_smoke() -> bool:
    mode = settings.android_smoke_test.strip().lower()
    if mode == "off":
        return False
    if mode == "force":
        return True
    return is_docker_available()


def parse_smoke_crash(log: str) -> dict:
    errors: list[dict] = []
    for line in log.splitlines():
        if "FATAL EXCEPTION" in line or "AndroidRuntime" in line:
            errors.append({"file": "runtime", "line": 0, "message": line.strip()})
    if not errors and log.strip():
        errors.append({"file": "runtime", "line": 0, "message": "smoke test crash (see smoke.log)"})
    return {"errors": errors[:5]}


def run_android_smoke(project_dir, package_id: str) -> SmokeResult:
    mode = settings.android_smoke_test.strip().lower()
    if mode == "off":
        return SmokeResult(ok=True, skipped=True, reason="smoke disabled (ANDROID_SMOKE_TEST=off)", log="")

    if mode == "auto" and not is_docker_available():
        return SmokeResult(
            ok=True,
            skipped=True,
            reason="smoke_skipped: docker not available",
            log="",
        )

    if not package_id:
        return SmokeResult(ok=True, skipped=True, reason="smoke_skipped: package id missing", log="")

    result = run_smoke_in_container(project_dir, package_id)
    if "smoke_skipped" in result.reasons:
        if mode == "force":
            return SmokeResult(
                ok=False,
                skipped=False,
                reason="smoke forced but environment unsupported",
                log=result.log,
            )
        return SmokeResult(
            ok=True,
            skipped=True,
            reason=result.log.strip() or "smoke_skipped",
            log=result.log,
        )
    if result.ok:
        return SmokeResult(ok=True, skipped=False, reason="", log=result.log)
    return SmokeResult(ok=False, skipped=False, reason="smoke test failed", log=result.log)

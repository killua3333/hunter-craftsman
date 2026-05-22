from __future__ import annotations

import logging
from pathlib import Path

from craftsman.config import settings
from craftsman.tools.shell import run_cmd

logger = logging.getLogger(__name__)


def run_beta_lane(project_dir: Path) -> tuple[bool, str]:
    if settings.skip_fastlane:
        return True, "fastlane skipped (SKIP_FASTLANE)"
    r = run_cmd(["which", "fastlane"], timeout=10.0)
    if r.exit_code != 0:
        return False, "fastlane not installed"
    result = run_cmd(
        ["fastlane", "beta"],
        cwd=str(project_dir),
        timeout=3600.0,
    )
    log = (result.stdout or "") + "\n" + (result.stderr or "")
    ok = result.exit_code == 0
    if not ok:
        logger.warning("fastlane beta failed: %s", log[-2000:])
    return ok, log

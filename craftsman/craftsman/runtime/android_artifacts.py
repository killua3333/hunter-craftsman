from __future__ import annotations

import shutil
from pathlib import Path


def find_debug_apk(project_dir: Path) -> Path | None:
    """Return the debug APK produced by the Android Gradle build."""
    output_dir = project_dir / "app" / "build" / "outputs" / "apk" / "debug"
    for name in ("app-debug.apk", "app-universal-debug.apk"):
        candidate = output_dir / name
        if candidate.is_file():
            return candidate
    return None


def export_debug_apk(project_dir: Path, artifacts_dir: Path) -> Path | None:
    """Copy the assembled debug APK into the run's exported artifacts."""
    source = find_debug_apk(project_dir)
    if source is None:
        return None
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    destination = artifacts_dir / "app-debug.apk"
    shutil.copy2(source, destination)
    return destination

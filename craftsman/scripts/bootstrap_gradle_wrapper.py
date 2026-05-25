"""Bootstrap Gradle wrapper files into templates/android-app/."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "android-app"
LOADER_FILES = (
    ("build.gradle.kts.j2", "build.gradle.kts"),
    ("settings.gradle.kts.j2", "settings.gradle.kts"),
    ("app/build.gradle.kts.j2", "app/build.gradle.kts"),
)


def _render_minimal_project(target: Path) -> None:
    ctx = {
        "app_name": "CraftsmanApp",
        "application_id": "com.craftsman.bootstrap",
        "min_android_sdk": "24",
        "build": "1",
        "version": "1.0.0",
    }
    for src_name, dst_name in LOADER_FILES:
        src = TEMPLATE / src_name
        dst = target / dst_name
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding="utf-8")
        for key, value in ctx.items():
            text = text.replace(f"{{{{ {key} }}}}", str(value))
        dst.write_text(text, encoding="utf-8")
    manifest = target / "app" / "src" / "main" / "AndroidManifest.xml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '  <application android:label="Bootstrap" />\n</manifest>\n',
        encoding="utf-8",
    )


def main() -> int:
    if shutil.which("gradle") is None:
        print("gradle not found on PATH; install Gradle or Android Studio to bootstrap wrapper", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "android-bootstrap"
        project.mkdir()
        _render_minimal_project(project)
        result = subprocess.run(
            ["gradle", "wrapper", "--gradle-version", "8.7"],
            cwd=str(project),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return result.returncode

        for name in ("gradlew", "gradlew.bat"):
            src = project / name
            if src.is_file():
                shutil.copy2(src, TEMPLATE / name)
        wrapper_dir = project / "gradle" / "wrapper"
        target_wrapper = TEMPLATE / "gradle" / "wrapper"
        if wrapper_dir.is_dir():
            if target_wrapper.exists():
                shutil.rmtree(target_wrapper)
            shutil.copytree(wrapper_dir, target_wrapper)

    print(f"Gradle wrapper installed under {TEMPLATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

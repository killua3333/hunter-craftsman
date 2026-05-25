from __future__ import annotations

import platform
import shutil
from pathlib import Path

from craftsman.config import settings
from craftsman.publisher.models import ReleaseBuildResult
from craftsman.runtime.docker_android import run_gradle_in_container, should_use_docker_backend
from craftsman.tools.shell import run_cmd


def _gradlew(project_dir: Path) -> Path:
    if platform.system() == "Windows":
        return project_dir / "gradlew.bat"
    return project_dir / "gradlew"


def ensure_gradle_wrapper(project_dir: Path) -> bool:
    """Create Gradle wrapper when system gradle is available."""
    gradlew = _gradlew(project_dir)
    if gradlew.is_file():
        return True
    if shutil.which("gradle") is None:
        return False
    result = run_cmd(["gradle", "wrapper", "--gradle-version", "8.7"], cwd=str(project_dir), timeout=300.0)
    return result.exit_code == 0 and gradlew.is_file()


def _run_local_bundle(project_dir: Path) -> ReleaseBuildResult:
    if not ensure_gradle_wrapper(project_dir):
        return ReleaseBuildResult(
            ok=False,
            reasons=["gradle wrapper missing and system gradle unavailable"],
            log="install Gradle or add gradlew to android template",
        )
    gradlew = _gradlew(project_dir)
    result = run_cmd([str(gradlew), "bundleRelease"], cwd=str(project_dir), timeout=1800.0)
    log = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.timed_out:
        log += "\n[gradle bundleRelease timed out]"
    built = project_dir / "app" / "build" / "outputs" / "bundle" / "release" / "app-release.aab"
    if result.exit_code == 0 and built.is_file():
        return ReleaseBuildResult(ok=True, aab_path=str(built), log=log)
    return ReleaseBuildResult(
        ok=False,
        log=log,
        reasons=["bundleRelease failed" if result.exit_code != 0 else "release aab not found"],
    )


def build_release_aab(project_dir: Path, *, dry_run: bool = False) -> ReleaseBuildResult:
    """
    Build signed release AAB via Gradle bundleRelease.
    In dry_run mode, skip Gradle and return a synthetic bundle path for pipeline testing.
    Uses Docker builder when ANDROID_BUILD_BACKEND=auto|docker and Docker is available.
    """
    artifacts_dir = project_dir.parent / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    output_aab = artifacts_dir / "app-release.aab"

    if dry_run:
        if not output_aab.is_file():
            import zipfile

            with zipfile.ZipFile(output_aab, "w") as zf:
                zf.writestr("META-INF/dry-run.txt", "agent-c dry run bundle")
        return ReleaseBuildResult(ok=True, aab_path=str(output_aab), log="dry-run bundle", dry_run=True)

    if should_use_docker_backend():
        docker_result = run_gradle_in_container(project_dir, "bundleRelease")
        built = project_dir / "app" / "build" / "outputs" / "bundle" / "release" / "app-release.aab"
        if docker_result.ok and built.is_file():
            shutil.copy2(built, output_aab)
            return ReleaseBuildResult(ok=True, aab_path=str(output_aab), log=docker_result.log)
        return ReleaseBuildResult(
            ok=False,
            log=docker_result.log,
            reasons=docker_result.reasons or ["docker bundleRelease failed"],
        )

    local = _run_local_bundle(project_dir)
    if local.ok and local.aab_path:
        built = Path(local.aab_path)
        if built.is_file():
            shutil.copy2(built, output_aab)
            return ReleaseBuildResult(ok=True, aab_path=str(output_aab), log=local.log)
    return local


def write_build_manifest(workspace: Path, build_info: dict) -> None:
    import json

    path = workspace / "publisher_build.json"
    path.write_text(json.dumps(build_info, ensure_ascii=False, indent=2), encoding="utf-8")

"""Docker 内 Android Gradle 构建 — Windows 无本机 SDK 时使用。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from craftsman.config import settings


@dataclass
class DockerGradleResult:
    ok: bool
    exit_code: int
    log: str
    reasons: list[str]


@lru_cache(maxsize=1)
def is_docker_available() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=60.0,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def should_use_docker_backend() -> bool:
    mode = settings.android_build_backend.strip().lower()
    if mode == "local":
        return False
    if mode == "docker":
        return is_docker_available()
    return is_docker_available()


def effective_skip_gradle_build() -> bool:
    """当显式 skip 或 auto 模式下既无 Docker 又无 local 编译能力时为 True。"""
    if settings.skip_gradle_build:
        return True
    mode = settings.android_build_backend.strip().lower()
    if mode == "docker":
        return not is_docker_available()
    if mode == "local":
        return False
    if is_docker_available():
        return False
    return True


def _container_project_path(project_dir: Path) -> tuple[Path, str]:
    project_dir = project_dir.resolve()
    workspace_mount = project_dir.parent
    return workspace_mount, "/workspace/project"


def run_gradle_in_container(
    project_dir: Path,
    gradle_task: str,
    *,
    extra_env: dict[str, str] | None = None,
) -> DockerGradleResult:
    if not is_docker_available():
        return DockerGradleResult(
            ok=False,
            exit_code=127,
            log="docker not available",
            reasons=["docker not available"],
        )

    workspace_mount, container_workdir = _container_project_path(project_dir)
    if not (project_dir / "gradlew").is_file() and not (project_dir / "gradlew.bat").is_file():
        return DockerGradleResult(
            ok=False,
            exit_code=127,
            log="gradle wrapper missing in project",
            reasons=["missing gradlew wrapper"],
        )

    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{workspace_mount}:/workspace",
        "-w",
        container_workdir,
        "-e",
        "GRADLE_USER_HOME=/tmp/gradle",
    ]
    secrets_dir = settings.secret_store_dir
    if secrets_dir.is_dir():
        cmd.extend(["-v", f"{secrets_dir.resolve()}:/secrets:ro"])
    if extra_env:
        for key, value in extra_env.items():
            cmd.extend(["-e", f"{key}={value}"])
    # Pass host proxy settings into the container (essential for network-restricted envs)
    import os as _os
    for _proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        _proxy_val = _os.environ.get(_proxy_var)
        if _proxy_val:
            cmd.extend(["-e", f"{_proxy_var}={_proxy_val}"])
    cmd.extend(
        [
            "--entrypoint",
            "/opt/gradle-8.7/bin/gradle",
            settings.docker_android_image,
            "--no-daemon",
            gradle_task,
        ]
    )

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(settings.docker_gradle_timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        log = (exc.stdout or "") + "\n" + (exc.stderr or "") + "\n[docker gradle timed out]"
        return DockerGradleResult(ok=False, exit_code=-1, log=log, reasons=["docker gradle timed out"])

    log = (proc.stdout or "") + "\n" + (proc.stderr or "")
    ok = proc.returncode == 0
    reasons: list[str] = []
    if not ok:
        reasons.append(f"gradle {gradle_task} failed in docker (exit {proc.returncode})")
    return DockerGradleResult(ok=ok, exit_code=proc.returncode, log=log, reasons=reasons)


def run_smoke_in_container(
    project_dir: Path,
    package_id: str,
) -> DockerGradleResult:
    """在 builder 镜像内跑冒烟测试（monkey）；不可用时返回 skipped。"""
    if not is_docker_available():
        return DockerGradleResult(
            ok=True,
            exit_code=0,
            log="smoke skipped: docker not available",
            reasons=["smoke_skipped"],
        )

    workspace_mount, container_workdir = _container_project_path(project_dir)
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{workspace_mount}:/workspace",
        "-w",
        container_workdir,
        settings.docker_android_image,
        "smoke",
        package_id,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(settings.android_smoke_timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        log = (exc.stdout or "") + "\n" + (exc.stderr or "") + "\n[smoke timed out]"
        return DockerGradleResult(ok=False, exit_code=-1, log=log, reasons=["smoke timed out"])

    log = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode == 2:
        return DockerGradleResult(ok=True, exit_code=0, log=log, reasons=["smoke_skipped"])
    if proc.returncode != 0:
        return DockerGradleResult(
            ok=False,
            exit_code=proc.returncode,
            log=log,
            reasons=["smoke test failed"],
        )
    return DockerGradleResult(ok=True, exit_code=0, log=log, reasons=[])

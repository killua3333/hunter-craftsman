"""Docker 内 Android Gradle 构建 — Windows 无本机 SDK 时使用。"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from craftsman.config import settings


@dataclass
class DockerGradleResult:
    ok: bool
    exit_code: int
    log: str
    reasons: list[str]


def is_docker_available() -> bool:
    """Probe Docker each time so a startup failure does not poison the process."""
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


def _container_proxy_url(value: str) -> str:
    """Translate a host-loopback proxy into an address Docker can reach."""
    raw = value.strip()
    if os.name != "nt" or not raw:
        return raw
    parsed = urlsplit(raw)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return raw
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    port = f":{parsed.port}" if parsed.port else ""
    return urlunsplit(
        (parsed.scheme, f"{userinfo}host.docker.internal{port}", parsed.path, parsed.query, parsed.fragment)
    )


def _docker_proxy_environment() -> dict[str, str]:
    """Return only proxies that the container can actually reach.

    HTTP_PROXY/HTTPS_PROXY are commonly configured for Play discovery and may
    point at a host-loopback client. Docker cannot use a proxy bound only to
    127.0.0.1, so builds use direct networking unless a dedicated build proxy
    is configured.
    """
    explicit_http = os.environ.get("ANDROID_BUILD_HTTP_PROXY", "").strip()
    explicit_https = os.environ.get("ANDROID_BUILD_HTTPS_PROXY", "").strip()
    if explicit_http or explicit_https:
        http = explicit_http or explicit_https
        https = explicit_https or explicit_http
        return {
            "HTTP_PROXY": _container_proxy_url(http),
            "HTTPS_PROXY": _container_proxy_url(https),
        }

    result: dict[str, str] = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        parsed = urlsplit(value)
        if parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
            continue
        result[key] = value
    return result


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
    gradle_tasks: str | Sequence[str],
    *,
    extra_env: dict[str, str] | None = None,
) -> DockerGradleResult:
    tasks = [gradle_tasks] if isinstance(gradle_tasks, str) else list(gradle_tasks)
    if not tasks or any(not task.strip() or any(char.isspace() for char in task) for task in tasks):
        return DockerGradleResult(
            ok=False,
            exit_code=2,
            log="invalid gradle task list",
            reasons=["gradle tasks must be passed as separate arguments"],
        )
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
    if extra_env:
        for key, value in extra_env.items():
            cmd.extend(["-e", f"{key}={value}"])
    # Pass host proxy settings into the container (essential for network-restricted envs)
    for proxy_var, proxy_value in _docker_proxy_environment().items():
        cmd.extend(["-e", f"{proxy_var}={proxy_value}"])
    cmd.extend(
        [
            "--entrypoint",
            "/opt/gradle-8.7/bin/gradle",
            settings.docker_android_image,
            "--no-daemon",
            *tasks,
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
        reasons.append(f"gradle {' '.join(tasks)} failed in docker (exit {proc.returncode})")
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
    cmd = _smoke_docker_command(project_dir, package_id)
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


def _smoke_docker_command(project_dir: Path, package_id: str) -> list[str]:
    workspace_mount, container_workdir = _container_project_path(project_dir)
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{workspace_mount}:/workspace",
        "-w",
        container_workdir,
    ]
    if os.name != "nt" and Path("/dev/kvm").exists():
        cmd.extend(["--device", "/dev/kvm:/dev/kvm"])
    cmd.extend([settings.docker_android_image, "smoke", package_id])
    return cmd

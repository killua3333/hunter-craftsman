from __future__ import annotations

import platform
from pathlib import Path

from craftsman.runtime.docker_android import (
    effective_skip_gradle_build,
    run_gradle_in_container,
    should_use_docker_backend,
)
from craftsman.tools import xcodebuild as xcode_tool
from craftsman.tools.shell import run_cmd
from craftsman.runtime.interfaces import BuildResult, ExecutionBackend
from craftsman.runtime.pool import choose_backend_target
from craftsman.config import settings


class DemoExecutionBackend:
    def __init__(self, target: str = "demo-local") -> None:
        self.target = target

    @property
    def mode(self) -> str:
        return "demo"

    def can_compile(self) -> bool:
        return False

    def compile(self, project_dir: Path, scheme: str) -> BuildResult:
        return BuildResult(
            ok=True,
            mode=self.mode,
            exit_code=0,
            reasons=[
                "compile skipped in demo mode",
            ],
        )

    def platform_note(self) -> str:
        return f"{xcode_tool.platform_note()} | target={self.target}"


class MacXcodeExecutionBackend:
    def __init__(self, target: str = "local-macos") -> None:
        self.target = target

    @property
    def mode(self) -> str:
        return "macos_xcode"

    def can_compile(self) -> bool:
        return True

    def compile(self, project_dir: Path, scheme: str) -> BuildResult:
        exit_code, log = xcode_tool.simulator_build(project_dir, scheme)
        return BuildResult(
            ok=exit_code == 0,
            mode=self.mode,
            exit_code=exit_code,
            log=log,
        )

    def platform_note(self) -> str:
        return f"{xcode_tool.platform_note()} | target={self.target}"


class AndroidGradleExecutionBackend:
    def __init__(self, target: str = "local-windows") -> None:
        self.target = target

    @property
    def mode(self) -> str:
        return "android_gradle"

    def can_compile(self) -> bool:
        return not effective_skip_gradle_build() and not should_use_docker_backend()

    def compile(self, project_dir: Path, scheme: str) -> BuildResult:
        gradlew = project_dir / "gradlew.bat"
        if platform.system() != "Windows":
            gradlew = project_dir / "gradlew"
        if not gradlew.is_file():
            return BuildResult(
                ok=False,
                mode=self.mode,
                exit_code=127,
                log="gradle wrapper missing",
                reasons=["missing gradlew wrapper"],
            )
        cmd = [str(gradlew), "assembleDebug"]
        # Inject proxy and Android SDK settings for Gradle.
        import os as _os
        env = dict(_os.environ)
        https_proxy = env.get("HTTPS_PROXY") or env.get("https_proxy") or ""
        if https_proxy:
            env["JAVA_TOOL_OPTIONS"] = "-Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=10808 -Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=10808"

        # Ensure Gradle sees the Android SDK even when it only comes from .env.
        android_home = (
            env.get("ANDROID_HOME")
            or env.get("ANDROID_SDK_ROOT")
            or settings.android_home
            or settings.android_sdk_root
            or ""
        )
        local_props = project_dir / "local.properties"
        if not android_home and local_props.is_file():
            for line in local_props.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("sdk.dir"):
                    android_home = line.split("=", 1)[-1].strip()
                    break
        if android_home:
            env["ANDROID_HOME"] = android_home
            env["ANDROID_SDK_ROOT"] = android_home
            sdk_line = f"sdk.dir={android_home.replace(chr(92), '/')}\n"
            local_props.write_text(sdk_line, encoding="utf-8")
        result = run_cmd(cmd, cwd=str(project_dir), timeout=1200.0, env=env)
        log = (result.stdout or "") + "\n" + (result.stderr or "")
        if result.timed_out:
            log += "\n[gradle timed out]"
        return BuildResult(
            ok=result.exit_code == 0,
            mode=self.mode,
            exit_code=result.exit_code,
            log=log,
        )

    def platform_note(self) -> str:
        return f"{xcode_tool.platform_note()} | target={self.target}"


class DockerGradleExecutionBackend:
    def __init__(self, target: str = "docker-local") -> None:
        self.target = target

    @property
    def mode(self) -> str:
        return "android_gradle_docker"

    def can_compile(self) -> bool:
        return should_use_docker_backend() and not effective_skip_gradle_build()

    def compile(self, project_dir: Path, scheme: str) -> BuildResult:
        docker_result = run_gradle_in_container(project_dir, "assembleDebug")
        return BuildResult(
            ok=docker_result.ok,
            mode=self.mode,
            exit_code=docker_result.exit_code,
            log=docker_result.log,
            reasons=docker_result.reasons,
        )

    def platform_note(self) -> str:
        return f"docker android builder | target={self.target}"


def select_execution_backend(requirement: dict | None = None) -> ExecutionBackend:
    target = choose_backend_target()
    platform_target = str(((requirement or {}).get("platform") or {}).get("target") or "android").lower()
    if platform_target == "ios" and xcode_tool.is_macos_with_xcode():
        return MacXcodeExecutionBackend(target=target)
    if platform_target == "ios":
        return DemoExecutionBackend(target=f"demo:{target}")
    if should_use_docker_backend():
        return DockerGradleExecutionBackend(target=f"docker:{target}")
    return AndroidGradleExecutionBackend(target=f"android:{target}")

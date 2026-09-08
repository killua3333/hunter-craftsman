from unittest.mock import MagicMock

from craftsman.runtime.docker_android import (
    _container_proxy_url,
    _docker_proxy_environment,
    _smoke_docker_command,
    is_docker_available,
    run_gradle_in_container,
    should_use_docker_backend,
)
from craftsman.config import settings


def test_is_docker_available_true(monkeypatch):
    monkeypatch.setattr(
        "craftsman.runtime.docker_android.subprocess.run",
        lambda *args, **kwargs: MagicMock(returncode=0, stdout="", stderr=""),
    )
    assert is_docker_available() is True


def test_docker_availability_is_rechecked_after_failure(monkeypatch):
    results = iter([MagicMock(returncode=1), MagicMock(returncode=0)])
    monkeypatch.setattr(
        "craftsman.runtime.docker_android.subprocess.run",
        lambda *args, **kwargs: next(results),
    )

    assert is_docker_available() is False
    assert is_docker_available() is True


def test_windows_loopback_proxy_is_reachable_from_container(monkeypatch):
    monkeypatch.setattr("craftsman.runtime.docker_android.os.name", "nt")

    assert _container_proxy_url("http://127.0.0.1:10808") == (
        "http://host.docker.internal:10808"
    )
    assert _container_proxy_url("http://proxy.example:8080") == "http://proxy.example:8080"


def test_play_loopback_proxy_is_not_passed_to_android_builder(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:10808")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:10808")
    monkeypatch.delenv("ANDROID_BUILD_HTTP_PROXY", raising=False)
    monkeypatch.delenv("ANDROID_BUILD_HTTPS_PROXY", raising=False)

    assert _docker_proxy_environment() == {}


def test_explicit_android_build_proxy_is_translated(monkeypatch):
    monkeypatch.setattr("craftsman.runtime.docker_android.os.name", "nt")
    monkeypatch.setenv("ANDROID_BUILD_HTTP_PROXY", "http://127.0.0.1:10808")
    monkeypatch.delenv("ANDROID_BUILD_HTTPS_PROXY", raising=False)

    assert _docker_proxy_environment() == {
        "HTTP_PROXY": "http://host.docker.internal:10808",
        "HTTPS_PROXY": "http://host.docker.internal:10808",
    }


def test_run_gradle_in_container_invokes_docker(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0, stdout="BUILD SUCCESSFUL", stderr="")

    monkeypatch.setattr("craftsman.runtime.docker_android.is_docker_available", lambda: True)
    monkeypatch.setattr("craftsman.runtime.docker_android.subprocess.run", fake_run)
    monkeypatch.setattr(settings, "docker_android_image", "test/android-builder")
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    monkeypatch.setattr(settings, "secret_store_dir", secret_dir)

    result = run_gradle_in_container(project, "assembleDebug")
    assert result.ok is True
    assert calls
    assert "docker" in calls[0]
    assert "assembleDebug" in calls[0]
    assert "/secrets:ro" not in " ".join(calls[0])


def test_run_gradle_in_container_passes_multiple_tasks_separately(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0, stdout="BUILD SUCCESSFUL", stderr="")

    monkeypatch.setattr("craftsman.runtime.docker_android.is_docker_available", lambda: True)
    monkeypatch.setattr("craftsman.runtime.docker_android.subprocess.run", fake_run)
    monkeypatch.setattr(settings, "docker_android_image", "test/android-builder")

    result = run_gradle_in_container(project, ["bundleRelease", "assembleDebug"])

    assert result.ok is True
    assert calls[0][-2:] == ["bundleRelease", "assembleDebug"]


def test_run_gradle_in_container_rejects_space_joined_tasks(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("craftsman.runtime.docker_android.is_docker_available", lambda: True)

    result = run_gradle_in_container(project, "bundleRelease assembleDebug")

    assert result.ok is False
    assert result.exit_code == 2
    assert "separate arguments" in " ".join(result.reasons)


def test_run_gradle_missing_wrapper(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr("craftsman.runtime.docker_android.is_docker_available", lambda: True)
    result = run_gradle_in_container(project, "assembleDebug")
    assert result.ok is False
    assert "gradlew" in result.log.lower() or "wrapper" in " ".join(result.reasons).lower()


def test_should_use_docker_backend_modes(monkeypatch):
    monkeypatch.setattr("craftsman.runtime.docker_android.is_docker_available", lambda: True)
    monkeypatch.setattr(settings, "android_build_backend", "docker")
    assert should_use_docker_backend() is True
    monkeypatch.setattr(settings, "android_build_backend", "local")
    assert should_use_docker_backend() is False


def test_smoke_command_maps_kvm_on_linux_when_available(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr("craftsman.runtime.docker_android.os.name", "posix")
    monkeypatch.setattr(
        "craftsman.runtime.docker_android.Path.exists",
        lambda path: str(path) == "/dev/kvm",
    )
    monkeypatch.setattr(settings, "docker_android_image", "test/android-builder")

    command = _smoke_docker_command(project, "com.test.app")

    assert command[-3:] == ["test/android-builder", "smoke", "com.test.app"]
    assert ["--device", "/dev/kvm:/dev/kvm"] == command[command.index("--device"):command.index("--device") + 2]


def test_smoke_command_does_not_map_kvm_on_windows(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr("craftsman.runtime.docker_android.os.name", "nt")

    command = _smoke_docker_command(project, "com.test.app")

    assert "--device" not in command

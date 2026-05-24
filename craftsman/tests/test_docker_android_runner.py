from unittest.mock import MagicMock

from craftsman.runtime.docker_android import (
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
    is_docker_available.cache_clear()
    assert is_docker_available() is True


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

    result = run_gradle_in_container(project, "assembleDebug")
    assert result.ok is True
    assert calls
    assert "docker" in calls[0]
    assert "assembleDebug" in calls[0]


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

from __future__ import annotations

import json
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from craftsman.coding.harness import run_workspace_coding_stage
from craftsman.config import settings


def test_workspace_coding_stage_is_scoped_and_audited(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    source = project / "app" / "src" / "main" / "MainActivity.kt"
    source.parent.mkdir(parents=True)
    source.write_text("class Before", encoding="utf-8")
    monkeypatch.setattr(settings, "coding_provider", "codex")
    monkeypatch.setattr(settings, "coding_agent_command_json", json.dumps(["codex", "exec", "-"]))

    def fake_run(command, **kwargs):
        assert command == ["codex", "exec", "-"]
        assert kwargs["cwd"] == str(project.resolve())
        assert "Work only in the current project directory" in kwargs["input"]
        source.write_text("class After", encoding="utf-8")
        return CompletedProcess(command, 0, stdout="done", stderr="")

    monkeypatch.setattr("craftsman.coding.harness.subprocess.run", fake_run)
    result = run_workspace_coding_stage(
        project_dir=project,
        workspace=workspace,
        stage="core_build",
        requirement={"app": {"name": "Test"}},
        context={"acceptance_actions": ["opens"]},
    )

    assert result.ok is True
    assert result.changed_files == ["app/src/main/MainActivity.kt"]
    assert (workspace / "coding" / "core_build-01.prompt.txt").is_file()
    assert (workspace / "coding" / "core_build-01.log").read_text(encoding="utf-8") == "done"


def test_workspace_coding_rejects_project_outside_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "coding_provider", "codex")
    monkeypatch.setattr(settings, "coding_agent_command_json", json.dumps(["codex", "exec", "-"]))
    with pytest.raises(ValueError, match="inside the run workspace"):
        run_workspace_coding_stage(
            project_dir=tmp_path / "outside",
            workspace=tmp_path / "workspace",
            stage="core_build",
            requirement={},
            context={},
        )


def test_workspace_coding_rejects_unapproved_executable(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(settings, "coding_provider", "command")
    monkeypatch.setattr(settings, "coding_agent_command_json", json.dumps(["powershell", "-Command", "x"]))
    with pytest.raises(ValueError, match="not allowed"):
        run_workspace_coding_stage(
            project_dir=project,
            workspace=workspace,
            stage="core_build",
            requirement={},
            context={},
        )


def test_workspace_coding_preserves_timeout_output(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(settings, "coding_provider", "codex")
    monkeypatch.setattr(settings, "coding_agent_command_json", json.dumps(["codex", "exec", "-"]))
    monkeypatch.setattr(settings, "coding_agent_timeout_seconds", 15.0)

    def fake_timeout(command, **kwargs):
        raise TimeoutExpired(command, 15, output=b"partial output", stderr=b"timed out")

    monkeypatch.setattr("craftsman.coding.harness.subprocess.run", fake_timeout)
    result = run_workspace_coding_stage(
        project_dir=project,
        workspace=workspace,
        stage="core_build",
        requirement={},
        context={},
    )

    assert result.ok is False
    assert result.error == "coding agent exceeded 15 seconds"
    assert (workspace / "coding" / "core_build-01.log").read_text(encoding="utf-8") == (
        "partial output\ntimed out"
    )

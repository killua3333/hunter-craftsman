from __future__ import annotations

import json
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from craftsman.coding.harness import _build_prompt, run_workspace_coding_stage
from craftsman.coding.deepseek_harness_runner import _notification_summary
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
        assert "GOOGLE_PLAY_SERVICE_ACCOUNT_FILE" not in kwargs["env"]
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
    assert (project / ".git").is_dir()


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


def test_workspace_coding_filters_release_credentials(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(settings, "coding_provider", "codex")
    monkeypatch.setattr(settings, "coding_agent_command_json", json.dumps(["codex", "exec", "-"]))
    monkeypatch.setenv("CODEX_API_KEY", "coding-key")
    monkeypatch.setenv("CODEX_APP_TOOLS_PIPE_PATH", "local-codex-pipe")
    monkeypatch.setenv("GOOGLE_PLAY_SERVICE_ACCOUNT_FILE", "publisher.json")
    monkeypatch.setenv("ANDROID_KEYSTORE_PASSWORD", "publisher-secret")

    def fake_run(command, **kwargs):
        assert kwargs["env"]["CODEX_API_KEY"] == "coding-key"
        assert kwargs["env"]["CODEX_APP_TOOLS_PIPE_PATH"] == "local-codex-pipe"
        assert "GOOGLE_PLAY_SERVICE_ACCOUNT_FILE" not in kwargs["env"]
        assert "ANDROID_KEYSTORE_PASSWORD" not in kwargs["env"]
        return CompletedProcess(command, 0, stdout="done", stderr="")

    monkeypatch.setattr("craftsman.coding.harness.subprocess.run", fake_run)
    result = run_workspace_coding_stage(
        project_dir=project,
        workspace=workspace,
        stage="product_polish",
        requirement={},
        context={},
    )
    assert result.ok


def test_core_build_cannot_pass_without_source_changes(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(settings, "coding_provider", "codex")
    monkeypatch.setattr(settings, "coding_agent_command_json", json.dumps(["codex", "exec", "-"]))
    monkeypatch.setattr(
        "craftsman.coding.harness.subprocess.run",
        lambda command, **kwargs: CompletedProcess(command, 0, stdout="done", stderr=""),
    )

    result = run_workspace_coding_stage(
        project_dir=project,
        workspace=workspace,
        stage="core_build",
        requirement={},
        context={},
    )

    assert result.ok is False
    assert result.exit_code == 3
    assert "without changing source files" in (result.error or "")


def test_workspace_coding_uses_live_log_runner_when_progress_is_requested(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    source = project / "app" / "src" / "main" / "MainActivity.kt"
    source.parent.mkdir(parents=True)
    source.write_text("class Before", encoding="utf-8")
    monkeypatch.setattr(settings, "coding_provider", "codex")
    monkeypatch.setattr(settings, "coding_agent_command_json", json.dumps(["codex", "exec", "-"]))
    observed: list[float] = []

    def fake_live_runner(**kwargs):
        kwargs["progress_callback"](65.0)
        source.write_text("class After", encoding="utf-8")
        kwargs["log_path"].write_text("working\ndone", encoding="utf-8")
        return 0, "working\ndone", None

    monkeypatch.setattr(
        "craftsman.coding.harness._run_coding_process_with_live_log",
        fake_live_runner,
    )
    result = run_workspace_coding_stage(
        project_dir=project,
        workspace=workspace,
        stage="core_build",
        requirement={},
        context={},
        progress_callback=observed.append,
    )

    assert result.ok is True
    assert observed == [65.0]
    assert (workspace / "coding" / "core_build-01.log").read_text(encoding="utf-8") == "working\ndone"


def test_codex_deepseek_uses_official_responses_provider_without_global_config(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    source = project / "app" / "src" / "main" / "MainActivity.kt"
    source.parent.mkdir(parents=True)
    source.write_text("class Before", encoding="utf-8")
    monkeypatch.setattr(settings, "coding_provider", "codex_deepseek")
    monkeypatch.setattr(settings, "codex_deepseek_model", "deepseek-v4-pro")
    monkeypatch.setattr(settings, "codex_deepseek_reasoning_effort", "high")
    monkeypatch.setattr(settings, "deepseek_api_key", "ds-test-key")
    monkeypatch.setattr(settings, "openai_api_key", "must-not-be-forwarded")
    monkeypatch.setenv("GOOGLE_PLAY_SERVICE_ACCOUNT_FILE", "publisher.json")

    def fake_run(command, **kwargs):
        joined = " ".join(command)
        assert command[:3] == ["codex", "exec", "--ignore-user-config"]
        assert 'model="deepseek-v4-pro"' in command
        assert 'model_providers.deepseek.wire_api="responses"' in command
        assert 'model_providers.deepseek.base_url="https://api.deepseek.com/"' in command
        assert "experimental_bearer_token" not in joined
        assert kwargs["env"]["DEEPSEEK_API_KEY"] == "ds-test-key"
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert "GOOGLE_PLAY_SERVICE_ACCOUNT_FILE" not in kwargs["env"]
        source.write_text("class After", encoding="utf-8")
        return CompletedProcess(command, 0, stdout="DeepSeek Codex done", stderr="")

    monkeypatch.setattr("craftsman.coding.harness.subprocess.run", fake_run)
    result = run_workspace_coding_stage(
        project_dir=project,
        workspace=workspace,
        stage="core_build",
        requirement={},
        context={},
    )

    assert result.ok is True
    assert result.provider == "codex_deepseek"
    assert (project / ".git").is_dir()


def test_codex_deepseek_rejects_unknown_model(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(settings, "coding_provider", "codex_deepseek")
    monkeypatch.setattr(settings, "codex_deepseek_model", "unverified-model")

    with pytest.raises(ValueError, match="unsupported Codex DeepSeek model"):
        run_workspace_coding_stage(
            project_dir=project,
            workspace=workspace,
            stage="core_build",
            requirement={},
            context={},
        )


def test_deepseek_harness_uses_official_sdk_runner_with_restricted_environment(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    source = project / "app" / "src" / "main" / "MainActivity.kt"
    source.parent.mkdir(parents=True)
    source.write_text("class Before", encoding="utf-8")
    monkeypatch.setattr(settings, "coding_provider", "deepseek_harness")
    monkeypatch.setattr(settings, "deepseek_harness_model", "deepseek-v4-pro")
    monkeypatch.setattr(settings, "deepseek_harness_reasoning_effort", "high")
    monkeypatch.setattr(settings, "deepseek_harness_max_tokens", 49152)
    monkeypatch.setattr(settings, "deepseek_harness_profile", "sdk")
    monkeypatch.setattr(settings, "deepseek_api_key", "ds-test-key")
    monkeypatch.setenv("GOOGLE_PLAY_SERVICE_ACCOUNT_FILE", "publisher.json")
    monkeypatch.setenv("ANDROID_KEYSTORE_PASSWORD", "publisher-secret")

    def fake_run(command, **kwargs):
        assert command[0].lower().endswith("python.exe") or command[0].endswith("python")
        assert command[1].endswith("deepseek_harness_runner.py")
        assert "--model" in command
        assert "deepseek-v4-pro" in command
        assert "--dsh-home" in command
        assert kwargs["env"]["DEEPSEEK_API_KEY"] == "ds-test-key"
        assert kwargs["env"]["DSH_TELEMETRY_MODE"] == "DISABLED"
        assert "GOOGLE_PLAY_SERVICE_ACCOUNT_FILE" not in kwargs["env"]
        assert "ANDROID_KEYSTORE_PASSWORD" not in kwargs["env"]
        source.write_text("class After", encoding="utf-8")
        return CompletedProcess(command, 0, stdout="DeepSeek Harness done", stderr="")

    monkeypatch.setattr("craftsman.coding.harness.subprocess.run", fake_run)
    result = run_workspace_coding_stage(
        project_dir=project,
        workspace=workspace,
        stage="core_build",
        requirement={},
        context={},
    )

    assert result.ok is True
    assert result.provider == "deepseek_harness"
    assert result.changed_files == ["app/src/main/MainActivity.kt"]
    assert (project / ".git").is_dir()


def test_deepseek_harness_rejects_unsafe_profile(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(settings, "coding_provider", "deepseek_harness")
    monkeypatch.setattr(settings, "deepseek_harness_profile", "sdk-minimal")

    with pytest.raises(ValueError, match="profile must be sdk"):
        run_workspace_coding_stage(
            project_dir=project,
            workspace=workspace,
            stage="core_build",
            requirement={},
            context={},
        )


def test_deepseek_harness_runner_drops_token_chunks_from_audit_log():
    class Notification:
        method = "session.event"
        payload = {"event": {"type": "assistant/chunk"}}

    assert _notification_summary(Notification()) is None


def test_deepseek_harness_windows_prompt_delegates_build_to_supervisor(monkeypatch):
    monkeypatch.setattr(settings, "coding_provider", "deepseek_harness")
    monkeypatch.setattr("craftsman.coding.harness.os.name", "nt")

    prompt = _build_prompt("core_build", {}, {})

    assert "do not call pwsh" in prompt
    assert "supervising pipeline performs the build" in prompt


def test_deepseek_flash_prompt_prioritizes_bounded_implementation(monkeypatch):
    monkeypatch.setattr(settings, "coding_provider", "deepseek_harness")
    monkeypatch.setattr(settings, "deepseek_harness_model", "deepseek-v4-flash")

    prompt = _build_prompt("core_build", {}, {})

    assert "Keep analysis brief" in prompt
    assert "Prefer a small complete implementation" in prompt

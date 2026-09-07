from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from craftsman.config import settings


_DEEPSEEK_MODEL_CATALOG = Path(__file__).with_name("deepseek_models.json")


@dataclass
class CodingRunResult:
    ok: bool
    provider: str
    stage: str
    exit_code: int
    duration_seconds: float
    changed_files: list[str]
    log_path: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_workspace_coding_enabled() -> bool:
    return settings.coding_provider.strip().lower() in {
        "deepseek_harness", "codex_deepseek", "codex", "claude", "command",
    }


def run_workspace_coding_stage(
    *,
    project_dir: Path,
    workspace: Path,
    stage: str,
    requirement: dict[str, Any],
    context: dict[str, Any],
    progress_callback: Callable[[float], None] | None = None,
) -> CodingRunResult:
    project = project_dir.resolve()
    root = workspace.resolve()
    if not project.is_relative_to(root):
        raise ValueError("coding project must stay inside the run workspace")

    provider = settings.coding_provider.strip().lower()
    command = _configured_command(workspace=root, stage=stage)
    if provider != "deepseek_harness":
        _validate_executable(command[0])
    if provider in {"deepseek_harness", "codex", "codex_deepseek"}:
        _ensure_project_git_boundary(project)
    coding_dir = workspace / "coding"
    coding_dir.mkdir(parents=True, exist_ok=True)
    attempt = len(list(coding_dir.glob(f"{stage}-*.json"))) + 1
    stem = f"{stage}-{attempt:02d}"
    prompt_path = coding_dir / f"{stem}.prompt.txt"
    log_path = coding_dir / f"{stem}.log"
    result_path = coding_dir / f"{stem}.json"
    prompt = _build_prompt(stage, requirement, context)
    prompt_path.write_text(prompt, encoding="utf-8")

    before = _source_fingerprints(project)
    started = time.monotonic()
    try:
        if progress_callback is None:
            completed = subprocess.run(
                command,
                cwd=str(project),
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=float(settings.coding_agent_timeout_seconds),
                shell=False,
                env=_coding_environment(provider),
            )
            exit_code = int(completed.returncode)
            output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
            error = None if exit_code == 0 else f"coding agent exited with code {exit_code}"
        else:
            exit_code, output, error = _run_coding_process_with_live_log(
                command=command,
                cwd=project,
                prompt=prompt,
                log_path=log_path,
                provider=provider,
                progress_callback=progress_callback,
            )
    except subprocess.TimeoutExpired as exc:
        exit_code = -1
        output = _combine_process_output(exc.stdout, exc.stderr)
        error = f"coding agent exceeded {settings.coding_agent_timeout_seconds:g} seconds"
    except OSError as exc:
        exit_code = -1
        output = str(exc)
        error = f"coding agent could not start: {exc}"
    duration = round(time.monotonic() - started, 3)
    log_path.write_text(output, encoding="utf-8")
    after = _source_fingerprints(project)
    changed = sorted(path for path, digest in after.items() if before.get(path) != digest)
    changed.extend(sorted(path for path in before if path not in after))
    changed = sorted(set(changed))
    if exit_code == 0 and stage == "core_build" and not changed:
        exit_code = 3
        error = "coding agent completed core_build without changing source files"
    result = CodingRunResult(
        ok=exit_code == 0,
        provider=provider,
        stage=stage,
        exit_code=exit_code,
        duration_seconds=duration,
        changed_files=changed,
        log_path=str(log_path),
        error=error,
    )
    result_path.write_text(json.dumps(result.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _run_coding_process_with_live_log(
    *,
    command: list[str],
    cwd: Path,
    prompt: str,
    log_path: Path,
    provider: str,
    progress_callback: Callable[[float], None],
) -> tuple[int, str, str | None]:
    """Stream CLI output to disk while reporting elapsed time to the run store."""
    timeout = float(settings.coding_agent_timeout_seconds)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=_coding_environment(provider),
        )
        if process.stdin is None:
            process.kill()
            process.wait()
            return -1, "coding agent stdin unavailable", "coding agent could not receive its task"
        process.stdin.write(prompt)
        process.stdin.close()
        while process.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed >= timeout:
                process.kill()
                process.wait()
                log_file.write("\n[coding agent timed out]\n")
                log_file.flush()
                output = log_path.read_text(encoding="utf-8", errors="replace")
                return -1, output, f"coding agent exceeded {timeout:g} seconds"
            progress_callback(elapsed)
            time.sleep(min(10.0, max(0.1, timeout - elapsed)))
        exit_code = int(process.returncode or 0)
    output = log_path.read_text(encoding="utf-8", errors="replace")
    error = None if exit_code == 0 else f"coding agent exited with code {exit_code}"
    return exit_code, output, error


def _combine_process_output(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    def decode(value: str | bytes | None) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value or ""

    standard = decode(stdout)
    error = decode(stderr)
    return standard + ("\n" + error if error else "")


def _coding_environment(provider: str) -> dict[str, str]:
    """Pass only process/runtime and coding-provider credentials to the coding CLI."""
    shared = {
        "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC",
        "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
        "TEMP", "TMP", "TMPDIR", "LOCALAPPDATA", "APPDATA",
        "LANG", "LC_ALL", "TERM", "COLORTERM", "NO_COLOR",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "no_proxy",
    }
    provider_keys = {
        "codex": {
            "CODEX_HOME", "CODEX_API_KEY", "OPENAI_API_KEY",
            "CODEX_APP_TOOLS_PIPE_PATH", "CODEX_CI",
            "CODEX_INTERNAL_ORIGINATOR_OVERRIDE", "CODEX_SESSION_ID",
            "CODEX_THREAD_ID", "CODEX_PERMISSION_PROFILE",
            "CODEX_SANDBOX_NETWORK_DISABLED", "CODEX_SHELL",
            "CODEX_MCP_NODE_PATH",
        },
        "codex_deepseek": {"DEEPSEEK_API_KEY"},
        "deepseek_harness": {"DEEPSEEK_API_KEY"},
        "claude": {"CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY"},
        "command": set(),
    }
    allowed = shared | provider_keys.get(provider, set())
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    if provider in {"codex_deepseek", "deepseek_harness"}:
        api_key = settings.resolved_deepseek_api_key()
        if api_key:
            environment["DEEPSEEK_API_KEY"] = api_key
    if provider == "deepseek_harness":
        environment.update({
            "DSH_TELEMETRY_MODE": "DISABLED",
            "DSH_TELEMETRY_DISABLED": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        })
    return environment


def _configured_command(*, workspace: Path, stage: str) -> list[str]:
    provider = settings.coding_provider.strip().lower()
    if provider == "deepseek_harness":
        model = settings.deepseek_harness_model.strip()
        effort = settings.deepseek_harness_reasoning_effort.strip().lower()
        profile = settings.deepseek_harness_profile.strip()
        if model not in {"deepseek-v4-flash", "deepseek-v4-pro"}:
            raise ValueError(f"unsupported DeepSeek Harness model: {model}")
        if effort not in {"off", "low", "high", "max"}:
            raise ValueError(f"unsupported DeepSeek Harness reasoning effort: {effort}")
        if profile != "sdk":
            raise ValueError("DeepSeek Harness profile must be sdk")
        if settings.deepseek_harness_max_tokens <= 0:
            raise ValueError("DeepSeek Harness max tokens must be positive")
        dsh_home = workspace / "coding" / "dsh-home"
        session_id = f"{workspace.name}-{stage}-{time.time_ns()}"
        return [
            sys.executable,
            str(Path(__file__).with_name("deepseek_harness_runner.py").resolve()),
            "--dsh-home",
            str(dsh_home.resolve()),
            "--model",
            model,
            "--reasoning-effort",
            effort,
            "--max-tokens",
            str(settings.deepseek_harness_max_tokens),
            "--timeout-seconds",
            str(settings.coding_agent_timeout_seconds),
            "--session-id",
            session_id,
        ]
    if provider == "codex_deepseek":
        if not _DEEPSEEK_MODEL_CATALOG.is_file():
            raise ValueError("DeepSeek Codex model catalog is missing")
        model = settings.codex_deepseek_model.strip()
        effort = settings.codex_deepseek_reasoning_effort.strip().lower()
        if model not in {"deepseek-v4-flash", "deepseek-v4-pro"}:
            raise ValueError(f"unsupported Codex DeepSeek model: {model}")
        if effort not in {"low", "high", "max"}:
            raise ValueError(f"unsupported Codex DeepSeek reasoning effort: {effort}")
        catalog = _DEEPSEEK_MODEL_CATALOG.resolve().as_posix()
        return [
            "codex", "exec", "--ignore-user-config", "--ephemeral",
            "--sandbox", "workspace-write", "--skip-git-repo-check",
            "-c", 'model_provider="deepseek"',
            "-c", f'model="{model}"',
            "-c", f'model_reasoning_effort="{effort}"',
            "-c", f'model_catalog_json="{catalog}"',
            "-c", 'model_providers.deepseek.name="deepseek"',
            "-c", 'model_providers.deepseek.base_url="https://api.deepseek.com/"',
            "-c", 'model_providers.deepseek.wire_api="responses"',
            "-c", 'model_providers.deepseek.env_key="DEEPSEEK_API_KEY"',
            "-c", "model_providers.deepseek.requires_openai_auth=false",
            "-",
        ]
    raw = (settings.coding_agent_command_json or "").strip()
    if not raw:
        raise ValueError("CODING_AGENT_COMMAND_JSON is required for workspace coding")
    try:
        command = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("CODING_AGENT_COMMAND_JSON must be a JSON string array") from exc
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("CODING_AGENT_COMMAND_JSON must be a non-empty JSON string array")
    return command


def _validate_executable(executable: str) -> None:
    allowed = {
        item.strip().lower()
        for item in settings.coding_agent_allowed_executables.split(",")
        if item.strip()
    }
    name = Path(executable).name.lower()
    if os.name == "nt" and name.endswith(".exe"):
        name = name[:-4]
    if name not in allowed:
        raise ValueError(f"coding agent executable is not allowed: {name}")


def _ensure_project_git_boundary(project: Path) -> None:
    """Prevent Codex from treating the parent platform repository as the app workspace."""
    if (project / ".git").exists():
        return
    try:
        exit_code = subprocess.call(
            ["git", "init", "--quiet"],
            cwd=str(project),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
    except OSError as exc:
        raise RuntimeError("git is required to isolate the Codex app workspace") from exc
    if exit_code != 0 or not (project / ".git").exists():
        raise RuntimeError("failed to create an isolated Git boundary for the Codex app workspace")


def _build_prompt(stage: str, requirement: dict[str, Any], context: dict[str, Any]) -> str:
    stage_goals = {
        "core_build": "Implement one complete primary user flow end to end. Keep scope small and make it buildable.",
        "feature_expansion": "Add only the remaining approved MVP features without weakening the working primary flow.",
        "product_polish": "Improve product-specific UI states, copy, accessibility, and edge cases without adding scope.",
        "repair": "Fix the supplied verification failures and preserve already passing behavior.",
    }
    payload = {
        "stage": stage,
        "goal": stage_goals.get(stage, "Complete this bounded product-development stage."),
        "requirement": requirement,
        "context": context,
    }
    platform_tool_note = ""
    if settings.coding_provider.strip().lower() == "deepseek_harness" and os.name == "nt":
        platform_tool_note = (
            "On this Windows runtime, do not call pwsh, bash, job_output, or any shell tool. "
            "Use read, glob, and str_replace_editor for all inspection and edits. "
            "Do not run Gradle or environment checks; the supervising pipeline performs the build after coding.\n"
        )
    execution_note = ""
    if (
        settings.coding_provider.strip().lower() == "deepseek_harness"
        and settings.deepseek_harness_model.strip() == "deepseek-v4-flash"
    ):
        execution_note = (
            "Keep analysis brief and implement the requested changes promptly. "
            "Inspect only source and build files needed for this stage; do not inspect store metadata. "
            "Prefer a small complete implementation over extended planning.\n"
        )
    return (
        "You are the implementation worker inside a supervised Android product pipeline.\n"
        "Work only in the current project directory. Inspect existing files before editing.\n"
        "Use Kotlin and Jetpack Compose. Do not publish, access credentials, or modify files outside this project.\n"
        "Do not replace working functionality with placeholders. Run relevant local checks when available.\n"
        + platform_tool_note
        + execution_note
        + "Finish the bounded stage below, then stop.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _source_fingerprints(project: Path) -> dict[str, str]:
    ignored_parts = {".git", ".gradle", "build", ".idea"}
    allowed_suffixes = {".kt", ".kts", ".xml", ".toml", ".properties", ".json"}
    result: dict[str, str] = {}
    for path in project.rglob("*"):
        if not path.is_file() or any(part in ignored_parts for part in path.parts):
            continue
        if path.suffix.lower() not in allowed_suffixes:
            continue
        rel = path.relative_to(project).as_posix()
        result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

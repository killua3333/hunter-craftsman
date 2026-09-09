"""测试环境不调用真实 DeepSeek API。"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_storage(monkeypatch, tmp_path):
    """Keep API and pipeline tests out of the operator's local database."""
    from craftsman.config import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "craftsman-test.db")
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "workspace")
    monkeypatch.setattr(settings, "callback_dir", tmp_path / "callbacks")


@pytest.fixture(autouse=True)
def _skip_native_builds_in_tests(monkeypatch):
    from craftsman.config import settings

    monkeypatch.setattr(settings, "skip_xcodebuild", True)
    monkeypatch.setattr(settings, "skip_gradle_build", True)


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch, request):
    if request.module.__name__ == "test_llm_routing":
        return
    monkeypatch.setattr("craftsman.config.settings.coding_provider", "deepseek_json")
    noop_analyze = lambda req: None
    noop_generate = lambda req, platform="ios": None
    noop_fix = lambda *args, **kwargs: None
    monkeypatch.setattr("craftsman.llm.generate_code_llm", noop_generate)
    monkeypatch.setattr("craftsman.llm.analyze_requirement_llm", noop_analyze)
    monkeypatch.setattr("craftsman.llm.fix_code_llm", noop_fix)
    monkeypatch.setattr("craftsman.gate.analyze_requirement_llm", noop_analyze)
    monkeypatch.setattr("craftsman.generator.scaffold.generate_code_llm", noop_generate)
    monkeypatch.setattr("craftsman.orchestrator.reflexion.fix_code_llm", noop_fix)


@pytest.fixture(autouse=True)
def _reset_api_rate_limiter():
    from craftsman.api import app as api_app

    api_app._rate_limiter._buckets.clear()

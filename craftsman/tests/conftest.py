"""测试环境不调用真实 DeepSeek API。"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _skip_native_builds_in_tests(monkeypatch):
    from craftsman.config import settings

    monkeypatch.setattr(settings, "skip_xcodebuild", True)
    monkeypatch.setattr(settings, "skip_gradle_build", True)


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch, request):
    if request.module.__name__ == "test_llm_routing":
        return
    noop_analyze = lambda req: None
    noop_generate = lambda req, platform="ios": None
    noop_fix = lambda *args, **kwargs: None
    monkeypatch.setattr("craftsman.llm.generate_code_llm", noop_generate)
    monkeypatch.setattr("craftsman.llm.analyze_requirement_llm", noop_analyze)
    monkeypatch.setattr("craftsman.llm.fix_code_llm", noop_fix)
    monkeypatch.setattr("craftsman.gate.analyze_requirement_llm", noop_analyze)
    monkeypatch.setattr("craftsman.generator.scaffold.generate_code_llm", noop_generate)
    monkeypatch.setattr("craftsman.orchestrator.reflexion.fix_code_llm", noop_fix)

from pathlib import Path
from unittest.mock import patch

from craftsman import llm
from craftsman.generator.scaffold import _render_android_templates


def test_analyze_requirement_uses_chat_model():
    with patch.object(llm, "_chat_json", return_value={"reasons": [], "suggested_rules": [], "open_questions": []}) as mock:
        llm.analyze_requirement_llm({"app": {"name": "T"}})
        assert mock.call_args.kwargs["model"] == llm.settings.deepseek_chat_model


def test_generate_code_uses_pro_model():
    payload = {
        "files": [
            {"path": "Sources/App.swift", "content": "@main struct XApp: App { var body: some Scene { WindowGroup { ContentView() } } }"},
            {"path": "Sources/ContentView.swift", "content": "struct ContentView: View { var body: some View { Text(\"Hi\") } }"},
            {"path": "Sources/Color+Hex.swift", "content": "import SwiftUI\nextension Color { static let brandPrimary = Color.blue }"},
        ]
    }
    with patch.object(llm, "_chat_json", return_value=payload) as mock:
        files = llm.generate_code_llm({"app": {"name": "T"}})
        assert mock.call_args.kwargs["model"] == llm.settings.deepseek_pro_model
        assert "Sources/App.swift" in files


def test_generate_code_android_requires_main_activity():
    payload = {
        "files": [
            {
                "path": "app/src/main/java/com/craftsman/MainActivity.kt",
                "content": "package com.craftsman\nclass MainActivity",
            },
        ]
    }
    with patch.object(llm, "_chat_json", return_value=payload) as mock:
        files = llm.generate_code_llm({"app": {"name": "T"}}, platform="android")
        assert files is not None
        assert "app/src/main/java/com/craftsman/MainActivity.kt" in files
        assert "Android" in mock.call_args.kwargs["system"] or "Kotlin" in mock.call_args.kwargs["system"]


def test_fix_code_uses_pro_model():
    with patch.object(llm, "_chat_json", return_value={"files": [{"path": "Sources/App.swift", "content": "x"}]}) as mock:
        llm.fix_code_llm({}, {"Sources/App.swift": "old"}, [{"message": "error"}], 1)
        assert mock.call_args.kwargs["model"] == llm.settings.deepseek_pro_model


def test_fix_code_android_uses_kotlin_prompt():
    with patch.object(llm, "_chat_json", return_value={"files": [{"path": "app/src/main/java/com/craftsman/MainActivity.kt", "content": "x"}]}) as mock:
        llm.fix_code_llm(
            {},
            {"app/src/main/java/com/craftsman/MainActivity.kt": "old"},
            [{"message": "error"}],
            1,
            platform="android",
        )
        assert "Kotlin" in mock.call_args.kwargs["system"]


def test_android_build_gradle_namespace_fixed(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    ctx = {
        "application_id": "com.hunter.pomodorotimer",
        "min_android_sdk": "24",
        "version": "1.0.0",
        "build": "1",
    }
    _render_android_templates(project, ctx, include_main_activity=False)
    gradle = (project / "app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'namespace = "com.craftsman"' in gradle
    assert 'applicationId = "com.hunter.pomodorotimer"' in gradle


def test_llm_usage_summary_collects_tokens_and_cost(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_price_chat_input_per_1k", 1.0)
    monkeypatch.setattr(llm.settings, "llm_price_chat_output_per_1k", 2.0)

    class _Usage:
        prompt_tokens = 100
        completion_tokens = 50
        total_tokens = 150

    class _Message:
        content = '{"ok": true}'

    class _Choice:
        message = _Message()

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()

    class _Completions:
        @staticmethod
        def create(**kwargs):
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(llm, "_client", lambda: _Client())
    llm.reset_usage_events()
    payload = llm._chat_json(
        model=llm.settings.deepseek_chat_model,
        system="s",
        user="u",
        temperature=0.1,
    )
    assert payload == {"ok": True}
    summary = llm.usage_summary()
    assert summary["calls"] == 1
    assert summary["prompt_tokens"] == 100
    assert summary["completion_tokens"] == 50
    assert summary["estimated_cost_usd"] == 0.2

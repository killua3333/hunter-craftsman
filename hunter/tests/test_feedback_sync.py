import json

from hunter.feedback.sync import sync_callbacks
from hunter.learning.weekly import run_weekly_learning


def test_sync_callbacks_imports_terminal(tmp_path, monkeypatch):
    callbacks = tmp_path / "callbacks"
    feedback = tmp_path / "feedback"
    callbacks.mkdir()
    feedback.mkdir()
    monkeypatch.setattr("hunter.feedback.store.FEEDBACK_DIR", feedback)

    payload = {
        "schema_version": "1.0",
        "opportunity_id": "calc-001",
        "revision": 1,
        "agent_b_status": "ready_for_release",
        "reasons": ["ok"],
    }
    (callbacks / "calc-001_r1_ready_for_release.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    (callbacks / "calc-001_r1_in_progress.json").write_text(
        json.dumps({**payload, "agent_b_status": "in_progress"}),
        encoding="utf-8",
    )

    result = sync_callbacks(callbacks_dir=callbacks)
    assert result["imported"] == 1
    assert (feedback / "calc-001_r1_ready_for_release.json").is_file()


def test_weekly_learning_includes_inline_learnings(tmp_path, monkeypatch):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "specialist_system.md").write_text("system", encoding="utf-8")
    (prompts / "specialist_learnings.md").write_text("learn", encoding="utf-8")
    (prompts / "weekly_learn.md").write_text("editor", encoding="utf-8")
    (prompts / "inline_learnings.md").write_text("- learning line", encoding="utf-8")

    monkeypatch.setattr("hunter.paths.PROMPTS_DIR", prompts)
    monkeypatch.setattr("hunter.learning.weekly.PROMPTS_DIR", prompts)
    monkeypatch.setattr("hunter.learning.weekly.REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr("hunter.learning.weekly.archive_feedback_batch", lambda paths, week_label: tmp_path / week_label)
    feedback_file = tmp_path / "feedback.json"
    feedback_file.write_text(json.dumps({"opportunity_id": "opp-1", "agent_b_status": "implementation_failed"}), encoding="utf-8")
    monkeypatch.setattr("hunter.learning.weekly.list_pending_feedback", lambda: [feedback_file])
    monkeypatch.setattr("hunter.learning.weekly.load_feedback_file", lambda path: {"opportunity_id": "opp-1", "agent_b_status": "implementation_failed"})

    captured: dict[str, str] = {}

    class _Response:
        content = "updated learnings"

    class _Model:
        def invoke(self, messages):
            captured["user"] = messages[1].content
            return _Response()

    monkeypatch.setattr("hunter.learning.weekly.get_chat_model", lambda: _Model())

    result = run_weekly_learning(min_feedback_count=1)
    assert result["skipped"] is False
    assert "当前 inline_learnings.md" in captured["user"]
    assert "learning line" in captured["user"]

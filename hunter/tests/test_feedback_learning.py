import json

from hunter.feedback.store import list_pending_feedback, save_feedback_raw
from hunter.prompts import load_system_prompt
from hunter.learning.weekly import run_weekly_learning


def test_load_system_prompt_includes_learnings():
    text = load_system_prompt()
    assert "Hunter" in text
    assert "---" in text
    assert len(text) > 200


def test_save_feedback_raw_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("hunter.feedback.store.FEEDBACK_DIR", tmp_path)
    data = {
        "opportunity_id": "test-1",
        "revision": 1,
        "agent_b_status": "implementation_failed",
        "reasons": ["too vague"],
        "schema_version": "1.0",
    }
    path = save_feedback_raw(data, filename="test.json")
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["opportunity_id"] == "test-1"
    assert list_pending_feedback() == [path]


def test_weekly_learning_skip_when_empty(monkeypatch):
    monkeypatch.setattr("hunter.learning.weekly.list_pending_feedback", lambda: [])
    result = run_weekly_learning(min_feedback_count=1)
    assert result["skipped"] is True

import json

from hunter.feedback.sync import sync_callbacks


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

from hunter.feedback.inline_learnings import append_inline_learning, load_inline_learnings


def test_inline_learnings_append_and_load(tmp_path, monkeypatch):
    learnings = tmp_path / "inline_learnings.md"
    monkeypatch.setattr("hunter.feedback.inline_learnings.INLINE_LEARNINGS_PATH", learnings)
    append_inline_learning(
        opportunity_id="opp-1",
        reason="implementation_failed",
        feedback={"agent_b_status": "implementation_failed", "reasons": ["build failed"]},
    )
    text = load_inline_learnings()
    assert "opp-1" in text
    assert "implementation_failed" in text

from unittest.mock import patch

from hunter.integrations.publisher import (
    TERMINAL_RELEASE_STATUSES,
    _play_console_fields,
    wait_for_release_completion,
)


def test_terminal_release_statuses_include_dry_run():
    assert "dry_run_complete" in TERMINAL_RELEASE_STATUSES
    assert "published" in TERMINAL_RELEASE_STATUSES


def test_wait_for_release_completion():
    calls = {"n": 0}

    def fake_status(_release_id, **kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            return {"release_id": "rel-1", "status": "building"}
        return {"release_id": "rel-1", "status": "dry_run_complete"}

    with patch("hunter.integrations.publisher.get_release_status", side_effect=fake_status):
        out = wait_for_release_completion(
            "rel-1",
            timeout_seconds=5.0,
            poll_interval_seconds=0.01,
        )
    assert out["status"] == "dry_run_complete"


def test_play_console_fields_prefers_submit_then_poll():
    submit = {"setup_sheet": "from submit", "play_console_setup_path": "/ws/setup.txt"}
    poll = {"status": "dry_run_complete", "agent_c": {"agent_c_status": "dry_run_complete"}}
    path, sheet = _play_console_fields(submit, poll)
    assert sheet == "from submit"
    assert path == "/ws/setup.txt"


def test_play_console_fields_from_poll_top_level():
    poll = {
        "status": "dry_run_complete",
        "setup_sheet": "from poll",
        "play_console_setup_path": "/ws/poll.txt",
    }
    path, sheet = _play_console_fields({}, poll)
    assert sheet == "from poll"
    assert path == "/ws/poll.txt"


def test_run_publish_pipeline_surfaces_poll_timeout():
    from hunter.integrations.publisher import run_publish_pipeline

    handoff = {
        "run_id": "run-1",
        "release_id": "rel-1",
        "platform": {"target": "android"},
        "compliance_metadata": {
            "subtitle": "s",
            "description": "d",
            "keywords": ["k"],
            "privacy_url": "https://app.pages.dev/privacy",
        },
    }
    feedback = {"run_id": "run-1", "release_handoff": handoff}
    prepare = {"accepted": True, "approval_required": False}
    submit = {"release_id": "rel-1", "status": "submitting", "agent_c_status": "building"}
    poll = {"release_id": "rel-1", "status": "building", "poll_timed_out": True}

    with patch("hunter.integrations.publisher.prepare_release", return_value=prepare), patch(
        "hunter.integrations.publisher.submit_release", return_value=submit
    ), patch("hunter.integrations.publisher.wait_for_release_completion", return_value=poll):
        out = run_publish_pipeline(feedback, timeout_seconds=1.0, poll_interval_seconds=0.01)
    assert out["poll_timed_out"] is True
    assert out["publish_status"] == "building"

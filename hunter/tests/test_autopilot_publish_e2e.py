"""Dry-run E2E: autopilot pipeline with publish poll (mocked HTTP)."""

from unittest.mock import patch

from tests.conftest import sample_blueprint


def test_autopilot_publish_dry_run_e2e():
    blueprint = sample_blueprint()
    progress_events = []
    implemented = {
        "agent_b_status": "implementation_complete",
        "opportunity_id": "auto-e2e",
        "revision": 1,
        "run_id": "run-e2e-1",
        "reasons": [],
        "verification": "demo",
        "release_handoff": {
            "run_id": "run-e2e-1",
            "platform": {"target": "android"},
        },
    }

    class FakeDiscoverySession:
        def send(self, _msg):
            return {"blueprint": blueprint, "answer": "{}"}

    publish_outcome = {
        "release_id": "rel-run-e2e-1",
        "publish_status": "dry_run_complete",
        "final_status": "dry_run_complete",
    }

    with (
        patch("hunter.agents.specialist.DiscoverySession", FakeDiscoverySession),
        patch(
            "hunter.orchestrator.pipeline.run_analyze",
            return_value={"agent_b_status": "accepted", "opportunity_id": "auto-e2e", "revision": 1},
        ),
        patch(
            "hunter.orchestrator.pipeline.start_implementation",
            return_value={"run_id": "run-e2e-1", "agent_b_status": "in_progress"},
        ),
        patch(
            "hunter.orchestrator.pipeline.wait_for_run_completion",
            return_value=implemented,
        ),
        patch(
            "hunter.orchestrator.pipeline.run_publish_pipeline",
            return_value=publish_outcome,
        ),
        patch("hunter.orchestrator.pipeline.save_feedback_raw"),
        patch("hunter.feedback.inline_learnings.append_inline_learning"),
    ):
        from hunter.orchestrator import run_autopilot_pipeline

        outcome = run_autopilot_pipeline(
            save_feedback=False,
            publish=True,
            progress_callback=progress_events.append,
        )

    assert outcome["mode"] == "autopilot"
    assert outcome["correlation_id"] == "run-e2e-1"
    assert outcome["publish"]["final_status"] == "dry_run_complete"
    phases = [event["phase"] for event in progress_events]
    assert "autopilot_discovery" in phases
    assert "analyze" in phases
    assert "analyze_result" in phases
    assert "implement" in phases
    assert "publish" in phases

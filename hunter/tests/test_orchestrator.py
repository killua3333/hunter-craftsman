from unittest.mock import patch

from tests.conftest import sample_blueprint


def test_orchestrator_clarify_then_implement():
    blueprint = sample_blueprint()
    needs_clarification = {
        "agent_b_status": "needs_clarification",
        "opportunity_id": "focus-001",
        "revision": 1,
        "reasons": ["ui_layout.screens 过简"],
        "suggested_rules": ["补充 screens"],
        "blueprint": {"open_questions": ["是否单屏？"]},
    }
    accepted = {"agent_b_status": "accepted", "opportunity_id": "focus-001", "revision": 2}
    implemented = {
        "agent_b_status": "ready_for_release",
        "opportunity_id": "focus-001",
        "revision": 2,
        "reasons": [],
    }

    session_results = [
        {"blueprint": blueprint, "answer": "{}"},
        {"blueprint": blueprint, "answer": "{}"},
    ]

    class FakeSession:
        def __init__(self):
            self._i = 0

        def send(self, _msg):
            out = session_results[min(self._i, len(session_results) - 1)]
            self._i += 1
            return out

    with (
        patch("hunter.orchestrator.pipeline.SpecialistSession", FakeSession),
        patch(
            "hunter.orchestrator.pipeline.run_analyze",
            side_effect=[needs_clarification, accepted],
        ),
        patch(
            "hunter.orchestrator.pipeline.run_sync_implementation",
            return_value=implemented,
        ),
        patch("hunter.orchestrator.pipeline.save_feedback_raw"),
    ):
        from hunter.orchestrator import run_opportunity_pipeline

        outcome = run_opportunity_pipeline(
            "做一个番茄钟",
            opportunity_id="focus-001",
            save_feedback=False,
        )

    assert outcome["rounds"] == 2
    assert outcome["revision"] == 2
    assert outcome["feedback"]["agent_b_status"] == "ready_for_release"


def test_run_blueprint_pipeline_from_chat_blueprint():
    blueprint = sample_blueprint()
    implemented = {
        "agent_b_status": "ready_for_release",
        "opportunity_id": "focus-001",
        "revision": 1,
        "reasons": [],
    }

    with (
        patch(
            "hunter.orchestrator.pipeline.run_analyze",
            return_value={"agent_b_status": "accepted", "opportunity_id": "focus-001", "revision": 1},
        ),
        patch(
            "hunter.orchestrator.pipeline.run_sync_implementation",
            return_value=implemented,
        ),
        patch("hunter.orchestrator.pipeline.save_feedback_raw"),
    ):
        from hunter.orchestrator import run_blueprint_pipeline

        outcome = run_blueprint_pipeline(
            blueprint,
            opportunity_id="focus-001",
            save_feedback=False,
        )

    assert outcome["rounds"] == 1
    assert outcome["feedback"]["agent_b_status"] == "ready_for_release"

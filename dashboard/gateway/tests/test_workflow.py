"""Tests for workflow state derivation."""

from __future__ import annotations

from workflow import derive_workflow


def _meta(status: str = "running") -> dict:
    return {"pipeline_id": "pl-test", "status": status}


def test_empty_state_returns_pending():
    wf = derive_workflow(
        hunter_events=[], craftsman_run=None, publisher_release=None, meta=_meta()
    )
    assert wf["active"] == "discover"
    assert all(s["status"] == "pending" for s in wf["steps"])
    assert wf["headline"] == "等待启动"


def test_blueprint_marks_discover_done():
    wf = derive_workflow(
        hunter_events=[
            {"type": "pipeline_start"},
            {"type": "blueprint", "accepted": True, "app_name": "X", "evidence_count": 2},
        ],
        craftsman_run=None,
        publisher_release=None,
        meta=_meta(),
    )
    by_name = {s["name"]: s for s in wf["steps"]}
    assert by_name["discover"]["status"] == "done"
    assert by_name["gate"]["status"] == "running"
    assert wf["active"] == "gate"


def test_gate_accepted_then_build_running():
    wf = derive_workflow(
        hunter_events=[
            {"type": "blueprint", "accepted": True, "app_name": "X", "evidence_count": 1},
            {"type": "gate_result", "revision": 1, "agent_b_status": "accepted"},
        ],
        craftsman_run={"status": "in_progress", "phase": "codegen", "phase_detail": "scaffolding"},
        publisher_release=None,
        meta=_meta(),
    )
    by_name = {s["name"]: s for s in wf["steps"]}
    assert by_name["gate"]["status"] == "done"
    assert by_name["build"]["status"] == "running"
    assert wf["active"] == "build"


def test_verify_phase_marks_build_done():
    wf = derive_workflow(
        hunter_events=[
            {"type": "blueprint", "accepted": True, "app_name": "X", "evidence_count": 1},
            {"type": "gate_result", "revision": 1, "agent_b_status": "accepted"},
        ],
        craftsman_run={"status": "in_progress", "phase": "verify"},
        publisher_release=None,
        meta=_meta(),
    )
    by_name = {s["name"]: s for s in wf["steps"]}
    assert by_name["build"]["status"] == "done"
    assert by_name["verify"]["status"] == "running"


def test_publish_complete_when_dry_run():
    wf = derive_workflow(
        hunter_events=[
            {"type": "blueprint", "accepted": True, "app_name": "X", "evidence_count": 1},
            {"type": "gate_result", "revision": 1, "agent_b_status": "accepted"},
            {"type": "publish_start"},
        ],
        craftsman_run={"status": "implementation_complete", "phase": "complete"},
        publisher_release={"status": "dry_run_complete", "agent_c_status": "dry_run_complete"},
        meta=_meta("complete"),
    )
    by_name = {s["name"]: s for s in wf["steps"]}
    assert by_name["publish"]["status"] == "done"
    assert wf["active"] == "publish"
    assert wf["headline"] == "全部完成"


def test_gate_rejected_fails_step():
    wf = derive_workflow(
        hunter_events=[
            {"type": "blueprint", "accepted": True, "app_name": "X", "evidence_count": 0},
            {"type": "gate_result", "revision": 2, "agent_b_status": "rejected"},
        ],
        craftsman_run=None,
        publisher_release=None,
        meta=_meta("failed"),
    )
    by_name = {s["name"]: s for s in wf["steps"]}
    assert by_name["gate"]["status"] == "failed"


def test_publisher_failed():
    wf = derive_workflow(
        hunter_events=[
            {"type": "blueprint", "accepted": True, "app_name": "X", "evidence_count": 1},
            {"type": "gate_result", "revision": 1, "agent_b_status": "accepted"},
            {"type": "publish_start"},
        ],
        craftsman_run={"status": "implementation_complete", "phase": "complete"},
        publisher_release={"status": "prepare_rejected", "agent_c_status": "failed"},
        meta=_meta("complete"),
    )
    by_name = {s["name"]: s for s in wf["steps"]}
    assert by_name["publish"]["status"] == "failed"

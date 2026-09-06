from __future__ import annotations

import json

from craftsman.orchestrator.production import (
    PRODUCTION_STAGES,
    ProductionSession,
    build_experience_spec,
    build_product_brief,
)
from craftsman.store.db import RunStore


def _requirement() -> dict:
    return {
        "opportunity_id": "opp-checklist",
        "revision": 2,
        "app": {"name": "Simple Checklist"},
        "features": [
            {"title": "Add a task"},
            {"title": "Complete a task"},
            {"title": "Filter tasks"},
            {"title": "Out-of-scope fourth feature"},
        ],
        "opportunity_meta": {
            "target_users": "People who need a minimal daily checklist",
            "competitor_gap": "Existing apps require accounts",
        },
    }


def test_product_artifacts_are_scoped_and_testable():
    requirement = _requirement()
    brief = build_product_brief(requirement)
    plan = {
        "primary_user_flow": "Add a task",
        "screens": ["Home", "Edit"],
        "screen_states": {"empty": "No tasks"},
        "user_actions": ["add task"],
        "acceptance_actions": ["task remains after restart"],
        "local_storage": "Room",
    }
    experience = build_experience_spec(requirement, plan)

    assert brief["target_users"].startswith("People")
    assert brief["problem"] == "Existing apps require accounts"
    assert brief["core_features"] == ["Add a task", "Complete a task", "Filter tasks"]
    assert experience["acceptance_actions"] == ["task remains after restart"]


def test_production_session_writes_stage_checkpoint_snapshot(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    run_id = store.create_run("opp-1", 1, _requirement())
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = ProductionSession(store, run_id, workspace)
    session.start("product_definition", inputs={"revision": 1})
    session.complete(
        "product_definition",
        outputs={"artifact": "product_brief.json"},
        acceptance={"passed": True},
    )

    snapshot = json.loads((workspace / "production_session.json").read_text(encoding="utf-8"))
    assert len(snapshot["stages"]) == len(PRODUCTION_STAGES)
    assert snapshot["stages"][0]["status"] == "completed"
    assert snapshot["stages"][1]["status"] == "pending"

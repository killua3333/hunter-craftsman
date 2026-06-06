import json
import os

import pytest

from hunter.observability.pipeline_run import (
    PIPELINE_RUNS_DIR,
    PipelineRunContext,
    finish_pipeline_run,
    start_pipeline_run,
)


@pytest.fixture(autouse=True)
def _isolate_pipeline_runs(tmp_path, monkeypatch):
    monkeypatch.setattr("hunter.observability.pipeline_run.PIPELINE_RUNS_DIR", tmp_path)
    monkeypatch.setenv("HUNTER_PIPELINE_TRACK", "1")


def test_pipeline_run_emits_and_finishes(tmp_path):
    ctx = start_pipeline_run(mode="test", question="demo")
    assert ctx is not None
    ctx.emit("gate_result", agent_b_status="accepted", revision=1)
    ctx.set_run_id("run-abc")
    url = finish_pipeline_run(
        {
            "accepted": True,
            "run_id": "run-abc",
            "feedback": {
                "agent_b_status": "implementation_complete",
                "release_handoff": {"release_id": "rel-run-abc"},
            },
            "publish": {"release_id": "rel-run-abc", "publish_status": "dry_run_complete"},
        }
    )
    assert url and "pipeline/" in url
    meta = json.loads((tmp_path / ctx.pipeline_id / "meta.json").read_text(encoding="utf-8"))
    assert meta["craftsman"]["run_id"] == "run-abc"
    assert meta["publisher"]["release_id"] == "rel-run-abc"
    assert meta["status"] == "complete"
    lines = (tmp_path / ctx.pipeline_id / "hunter.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2


def test_pipeline_track_disabled(monkeypatch):
    monkeypatch.setenv("HUNTER_PIPELINE_TRACK", "0")
    assert start_pipeline_run(mode="x") is None

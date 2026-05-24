import json
from pathlib import Path

from craftsman.config import settings
from craftsman.orchestrator.pipeline import run_implementation
from craftsman.store.db import RunStore

SAMPLE = Path(__file__).parent.parent / "examples" / "requirement.sample.json"


def test_windows_demo_mode_generates_artifacts(tmp_path, monkeypatch):
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))

    monkeypatch.setattr(settings, "skip_xcodebuild", True)
    monkeypatch.setattr(settings, "skip_fastlane", True)
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "workspace")
    monkeypatch.setattr(settings, "callback_dir", tmp_path / "callbacks")

    store = RunStore(db_path=tmp_path / "runs.db")
    run_id = store.create_run(
        opportunity_id=req["opportunity_id"],
        revision=req["revision"],
        requirement=req,
    )

    fb = run_implementation(store, run_id)
    payload = fb.to_agent_a_dict()

    assert payload["agent_b_status"] == "implementation_complete"
    assert payload.get("verification") == "demo"
    artifacts = payload["artifacts"]
    assert artifacts["workspace"].startswith(("object://", "file://"))
    assert artifacts["demo_html"].startswith(("object://", "file://"))
    assert artifacts["preview_html"].startswith(("object://", "file://"))
    local = artifacts["local_paths"]
    assert Path(local["demo_html"]).is_file()
    assert Path(local["preview_html"]).is_file()
    preview = Path(local["preview_html"]).read_text(encoding="utf-8").lower()
    assert "<script" in preview
    assert Path(local["icon"]).is_file()
    assert len(artifacts["screenshots"]) >= 1
    assert len(local["screenshots"]) >= 1
    assert "release_handoff" in payload
    assert payload["release_handoff"]["platform"]["target"] == "android"

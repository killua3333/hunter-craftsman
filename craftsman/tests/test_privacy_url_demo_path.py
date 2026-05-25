import json
from pathlib import Path
from unittest.mock import patch

from craftsman.config import settings
from craftsman.orchestrator.pipeline import run_implementation
from craftsman.publisher.privacy_policy import is_placeholder_privacy_url
from craftsman.store.db import RunStore

SAMPLE = Path(__file__).parent.parent / "examples" / "requirement.sample.json"


def test_demo_path_deploys_privacy_url_before_handoff(tmp_path, monkeypatch):
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    monkeypatch.setattr(settings, "skip_xcodebuild", True)
    monkeypatch.setattr(settings, "skip_fastlane", True)
    monkeypatch.setattr(settings, "skip_gradle_build", True)
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "workspace")
    monkeypatch.setattr(settings, "callback_dir", tmp_path / "callbacks")
    monkeypatch.setenv("SKIP_GRADLE_BUILD", "true")

    store = RunStore(db_path=tmp_path / "runs.db")
    run_id = store.create_run(
        opportunity_id=req["opportunity_id"],
        revision=req["revision"],
        requirement=req,
    )

    fake_url = "https://com-hunter-timer.pages.dev/privacy"

    def _fake_ensure(req, workspace):
        req.setdefault("store", {})["privacy_url"] = fake_url
        return {"ok": True, "url": fake_url}

    with patch(
        "craftsman.publisher.privacy_policy.ensure_privacy_url",
        side_effect=_fake_ensure,
    ):
        fb = run_implementation(store, run_id)

    handoff = fb.to_agent_a_dict()["release_handoff"]
    privacy_url = handoff["compliance_metadata"]["privacy_url"]
    assert not is_placeholder_privacy_url(privacy_url)
    assert privacy_url == fake_url

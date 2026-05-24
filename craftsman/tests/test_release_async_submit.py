import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from craftsman.api.app import create_app
from craftsman.config import settings

SAMPLE = Path(__file__).parent.parent / "examples" / "requirement.sample.json"


def test_release_submit_returns_immediately_and_worker_completes(monkeypatch):
    monkeypatch.setattr(settings, "release_require_human_approval", False)
    monkeypatch.setattr(settings, "release_require_policy_checks", True)
    monkeypatch.setattr(settings, "publisher_dry_run", True)

    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with TestClient(create_app()) as client:
        sync = client.post("/v1/runs/sync-implement", json={"requirement": req})
        assert sync.status_code == 200
        handoff = dict(sync.json()["release_handoff"])
        release_id = f"rel-{handoff['run_id']}"
        handoff["release_id"] = release_id

        prepare = client.post("/v1/releases/prepare", json=handoff)
        assert prepare.status_code == 200
        assert prepare.json()["accepted"] is True

        started = time.monotonic()
        submit = client.post(f"/v1/releases/{release_id}/submit")
        elapsed = time.monotonic() - started
        assert submit.status_code == 200
        assert elapsed < 5.0
        body = submit.json()
        assert body["status"] == "submitting"
        assert body["agent_c_status"] == "building"

        final_status = "submitting"
        for _ in range(100):
            status = client.get(f"/v1/releases/{release_id}")
            final_status = status.json()["status"]
            if final_status in ("dry_run_complete", "published", "failed"):
                break
            time.sleep(0.05)
        assert final_status == "dry_run_complete"

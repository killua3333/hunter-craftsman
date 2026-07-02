import json
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from craftsman.api.app import create_app
from craftsman.config import settings
from craftsman.store.db import RunStore
from craftsman.worker import BackgroundWorker, _should_release_package_for_agent_c

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


def test_release_failure_keeps_release_handoff_for_requeue(monkeypatch):
    store = RunStore()
    worker = BackgroundWorker(store)
    release_id = "rel-failure-keep-handoff"
    handoff = {"release_id": release_id, "platform": {"target": "android"}, "run_id": "run-keep"}
    store.record_release_policy_check(release_id, passed=True, issues=[])
    store.record_release_approval(release_id, decision="approved", approved_by="tester", note=None)
    store.upsert_release_state(
        release_id,
        status="submitting",
        details={"release_handoff": handoff, "platform_target": "android"},
        updated_by="tester",
    )

    with patch("craftsman.worker.run_android_release", side_effect=RuntimeError("simulated release failure")):
        worker._process_release(release_id, lease_token="lease-test")

    release = store.get_release_state(release_id)
    assert release is not None
    assert release["status"] == "failed"
    assert release["details"]["release_handoff"]["release_id"] == release_id
    assert release["details"]["message"] == "simulated release failure"


def test_agent_c_package_release_policy():
    assert _should_release_package_for_agent_c("failed", "package_not_precreated") is True
    assert _should_release_package_for_agent_c("failed", "service_account_permission") is True
    assert _should_release_package_for_agent_c("failed", "version_code_conflict") is False
    assert _should_release_package_for_agent_c("failed", "play_api_transient") is False
    assert _should_release_package_for_agent_c("internal_submitted", None) is False
    assert _should_release_package_for_agent_c("dry_run_complete", None) is False
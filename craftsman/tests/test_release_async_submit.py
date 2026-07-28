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


def test_release_submit_returns_immediately_and_worker_completes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr(settings, "release_require_human_approval", False)
    monkeypatch.setattr(settings, "release_require_policy_checks", True)
    monkeypatch.setattr(settings, "package_pool", "")
    monkeypatch.setattr(settings, "privacy_policy_url", "https://privacy.test/policy")

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

        fake_result = {
            "agent_c_status": "internal_submitted",
            "platform_target": "android",
            "track": "internal",
            "release_handoff": handoff,
            "release_bundle": handoff.get("release_bundle", {}),
            "failure_class": None,
        }
        with patch("craftsman.worker.run_android_release", return_value=fake_result):
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
                if final_status in ("internal_submitted", "published", "failed"):
                    break
                time.sleep(0.05)
            assert final_status == "internal_submitted"


def test_release_failure_keeps_release_handoff_for_requeue(monkeypatch):
    store = RunStore()
    worker = BackgroundWorker(store)
    monkeypatch.setattr("craftsman.worker.check_release_compliance_metadata", lambda handoff: {"passed": True, "issues": []})
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


def test_auto_release_enqueues_internal_submit_after_quality_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr("craftsman.worker.check_release_compliance_metadata", lambda handoff: {"passed": True, "issues": []})
    store = RunStore()
    worker = BackgroundWorker(store)
    requirement = {
        "opportunity_id": "opp-auto",
        "revision": 1,
        "automation": {"auto_release": True, "approved_by": "discovery_auto_publish", "release_track": "internal"},
    }
    release_id = "rel-auto-run"
    handoff = {
        "schema_version": "1.0",
        "run_id": "run-auto-placeholder",
        "release_id": release_id,
        "opportunity_id": "opp-auto",
        "revision": 1,
        "platform": {"target": "android"},
        "requirement_digest": "sha256:auto",
        "release_bundle": {"project_path": "object://local/runs/run-auto-placeholder/project"},
        "build_provenance": {"backend": "android_gradle", "backend_target": "android", "craftsman_version": "test"},
        "compliance_metadata": {
            "subtitle": "Auto",
            "description": "Auto publish test app",
            "keywords": ["auto"],
            "privacy_url": "https://example.com/privacy",
        },
        "quality_score": 82,
        "release_ready": False,
        "quality_report": {
            "quality_score": 82,
            "release_ready": False,
            "failure_classes": ["scope_too_large"],
        },
        "app": {"bundle_id": "com.example.autopublish"},
    }
    run_id = store.create_run("opp-auto", 1, requirement, status="needs_polish")
    handoff["run_id"] = run_id
    handoff["release_bundle"]["project_path"] = f"object://local/runs/{run_id}/project"
    store.update_run(run_id, feedback={"release_handoff": handoff})

    worker._maybe_enqueue_auto_release(run_id)

    release = store.get_release_state(release_id)
    assert release is not None
    assert release["status"] == "submitting"
    assert release["details"]["auto_release"] is True
    jobs = store.list_release_jobs(limit=10)
    assert any(job["release_id"] == release_id and job["status"] == "pending" for job in jobs)


def test_agent_c_package_release_policy():
    assert _should_release_package_for_agent_c("failed", "package_not_precreated") is True
    assert _should_release_package_for_agent_c("failed", "service_account_permission") is True
    assert _should_release_package_for_agent_c("failed", "version_code_conflict") is False
    assert _should_release_package_for_agent_c("failed", "play_api_transient") is False
    assert _should_release_package_for_agent_c("internal_submitted", None) is False

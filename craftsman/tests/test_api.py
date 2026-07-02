import time

import json
from pathlib import Path

from fastapi.testclient import TestClient

from craftsman.api import app as api_app
from craftsman.api.app import create_app
from craftsman.config import settings

SAMPLE = Path(__file__).parent.parent / "examples" / "requirement.sample.json"


def test_analyze_endpoint():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    client = TestClient(create_app())
    resp = client.post(f"/v1/opportunities/{req['opportunity_id']}/analyze", json=req)
    assert resp.status_code == 200
    body = resp.json()
    assert body["blueprint"]["accepted"] is True
    assert body["agent_b_status"] == "accepted"
    assert body["contract_version"] == "1.0"


def test_health_reports_repaired_release_jobs():
    with TestClient(create_app()) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "repaired_release_jobs" in body["runs"]


def test_readyz_endpoint():
    with TestClient(create_app()) as client:
        resp = client.get("/readyz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ready"] is True
        assert body["checks"]["workspace_ok"] is True
        assert body["checks"]["callbacks_ok"] is True
        assert body["checks"]["database_ok"] is True
        assert "repaired_release_jobs" in body


def test_analyze_rejects_incomplete(monkeypatch):
    from craftsman.config import settings

    monkeypatch.setattr(settings, "gate_mode", "strict")
    monkeypatch.setattr(settings, "gate_auto_accept", False)
    req = {
        "schema_version": "1.0",
        "opportunity_id": "bad-001",
        "revision": 1,
        "app": {"name": "Bad", "bundle_id": "com.bad.app"},
        "features": [{"id": "x", "type": "list", "title": "X"}],
    }
    client = TestClient(create_app())
    resp = client.post("/v1/opportunities/bad-001/analyze", json=req)
    assert resp.status_code == 200
    assert resp.json()["blueprint"]["accepted"] is False


def test_error_envelope_for_mismatch():
    req = {"opportunity_id": "foo"}
    client = TestClient(create_app())
    resp = client.post("/v1/opportunities/bar/analyze", json=req)
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"]["code"] == "opportunity_id_mismatch"


def test_contract_version_unsupported():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    client = TestClient(create_app())
    resp = client.post(
        f"/v1/opportunities/{req['opportunity_id']}/analyze",
        json=req,
        headers={"X-Contract-Version": "9.9"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"]["code"] == "contract_version_unsupported"


def test_api_token_auth(monkeypatch):
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    monkeypatch.setattr(settings, "api_token", "secret-token")
    client = TestClient(create_app())
    unauthorized = client.post(f"/v1/opportunities/{req['opportunity_id']}/analyze", json=req)
    assert unauthorized.status_code == 401
    authorized = client.post(
        f"/v1/opportunities/{req['opportunity_id']}/analyze",
        json=req,
        headers={"X-API-Token": "secret-token"},
    )
    assert authorized.status_code == 200


def test_api_token_from_secret_store(tmp_path, monkeypatch):
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    store = tmp_path / "secrets"
    store.mkdir(parents=True, exist_ok=True)
    (store / "API_TOKEN").write_text("secret-from-file", encoding="utf-8")
    monkeypatch.setattr(settings, "secret_provider", "file")
    monkeypatch.setattr(settings, "secret_store_dir", store)
    monkeypatch.setattr(settings, "api_token", None)
    client = TestClient(create_app())
    denied = client.post(f"/v1/opportunities/{req['opportunity_id']}/analyze", json=req)
    assert denied.status_code == 401
    allowed = client.post(
        f"/v1/opportunities/{req['opportunity_id']}/analyze",
        json=req,
        headers={"X-API-Token": "secret-from-file"},
    )
    assert allowed.status_code == 200


def test_sync_implement_endpoint():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with TestClient(create_app()) as client:
        resp = client.post("/v1/runs/sync-implement", json={"requirement": req})
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_b_status"] == "implementation_complete"
        assert "release_handoff" in body
        assert body["release_handoff"]["platform"]["target"] == "android"


def test_release_endpoints_agent_c_android(monkeypatch):
    monkeypatch.setattr(settings, "release_require_human_approval", True)
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
        assert prepare.json()["platform_target"] == "android"
        assert prepare.json()["policy"]["passed"] is True
        assert prepare.json()["approval_required"] is True

        submit = client.post(f"/v1/releases/{release_id}/submit")
        assert submit.status_code == 409
        assert submit.json()["detail"]["error"]["code"] == "release_requires_human_approval"

        approve = client.post(
            f"/v1/releases/{release_id}/approve",
            json={"approved_by": "qa-owner", "decision": "approved", "note": "ship it"},
        )
        assert approve.status_code == 200
        assert approve.json()["status"] == "approval_recorded"
        assert approve.json()["approval"]["decision"] == "approved"

        submit_after = client.post(f"/v1/releases/{release_id}/submit")
        assert submit_after.status_code == 200
        body = submit_after.json()
        assert body["status"] == "submitting"
        assert body["agent_c_status"] == "building"
        assert body["platform_target"] == "android"
        assert body["approval"]["decision"] == "approved"
        assert body["policy"]["passed"] is True

        final_status = "submitting"
        for _ in range(100):
            status = client.get(f"/v1/releases/{release_id}")
            assert status.status_code == 200
            final_status = status.json()["status"]
            if final_status in ("dry_run_complete", "published", "failed"):
                break
            time.sleep(0.05)
        assert final_status == "dry_run_complete"

        status = client.get(f"/v1/releases/{release_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "dry_run_complete"
        assert status.json()["agent_c_status"] == "dry_run_complete"
        assert status.json()["approval"]["decision"] == "approved"
        assert status.json()["policy"]["passed"] is True
        assert status.json()["state"]["status"] == "dry_run_complete"
        agent_c = status.json().get("agent_c") or {}
        assert agent_c.get("release_bundle", {}).get("aab_path")


def test_release_submit_blocked_by_policy_failure(monkeypatch):
    monkeypatch.setattr(settings, "release_require_human_approval", True)
    monkeypatch.setattr(settings, "release_require_policy_checks", True)
    client = TestClient(create_app())
    release_id = "rel-bad"
    bad = {
        "run_id": "run-bad",
        "release_id": release_id,
        "compliance_metadata": {"subtitle": "", "description": "", "keywords": [], "privacy_url": ""},
    }
    prepare = client.post("/v1/releases/prepare", json=bad)
    assert prepare.status_code == 200
    assert prepare.json()["accepted"] is False
    assert prepare.json()["policy"]["passed"] is False
    approve = client.post(
        f"/v1/releases/{release_id}/approve",
        json={"approved_by": "qa-owner", "decision": "approved"},
    )
    assert approve.status_code == 200
    submit = client.post(f"/v1/releases/{release_id}/submit")
    assert submit.status_code == 409
    assert submit.json()["detail"]["error"]["code"] == "release_policy_check_failed"


def test_release_submit_blocks_low_quality_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr(settings, "release_require_human_approval", False)
    monkeypatch.setattr(settings, "release_require_policy_checks", True)
    release_id = "rel-low-quality"
    handoff = {
        "schema_version": "1.0",
        "run_id": "run-low-quality",
        "release_id": release_id,
        "opportunity_id": "opp-low-quality",
        "revision": 1,
        "platform": {"target": "android"},
        "app": {"name": "Low Quality", "bundle_id": "com.example.lowquality"},
        "requirement_digest": "sha256:test",
        "release_bundle": {
            "project_path": "object://local/runs/run-low-quality/project",
            "metadata_path": "object://local/runs/run-low-quality/project/play/metadata",
        },
        "build_provenance": {
            "backend": "android_gradle",
            "backend_target": "android",
            "craftsman_version": "0.1.0",
            "codegen_model": "test-model",
        },
        "compliance_metadata": {
            "subtitle": "Test",
            "description": "Test app description",
            "keywords": ["test"],
            "privacy_url": "https://privacy.lowquality.test/policy",
        },
        "quality_score": 62,
        "release_ready": False,
        "quality_report": {
            "quality_score": 62,
            "release_ready": False,
            "failure_classes": ["weak_core_flow"],
        },
    }

    with TestClient(create_app()) as client:
        prepared = client.post("/v1/releases/prepare", json=handoff)
        assert prepared.status_code == 200
        assert prepared.json()["accepted"] is True

        submit = client.post(f"/v1/releases/{release_id}/submit")
        assert submit.status_code == 200
        body = submit.json()
        assert body["status"] == "needs_manual_action"
        assert body["quality_blocker"]["quality_score"] == 62

        state = client.get(f"/v1/releases/{release_id}").json()["state"]
        assert state["status"] == "needs_manual_action"


def test_release_handoff_validation_endpoint():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with TestClient(create_app()) as client:
        sync = client.post("/v1/runs/sync-implement", json={"requirement": req})
        assert sync.status_code == 200
        handoff = sync.json().get("release_handoff")
        assert isinstance(handoff, dict)
        valid = client.post("/v1/releases/validate-handoff", json=handoff)
        assert valid.status_code == 200
        assert valid.json()["accepted"] is True

        invalid = dict(handoff)
        invalid.pop("release_bundle", None)
        bad = client.post("/v1/releases/validate-handoff", json=invalid)
        assert bad.status_code == 400
        assert bad.json()["detail"]["error"]["code"] == "invalid_release_handoff"


def test_run_events_endpoint():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with TestClient(create_app()) as client:
        run = client.post(
            f"/v1/opportunities/{req['opportunity_id']}/implement",
            json={"opportunity_id": req["opportunity_id"], "requirement": req},
        )
        assert run.status_code == 200
        run_id = run.json()["run_id"]

        events = client.get(f"/v1/runs/{run_id}/events")
        assert events.status_code == 200
        body = events.json()
        assert body["run_id"] == run_id
        assert isinstance(body["events"], list)
        assert "next_after_id" in body
        if body["events"]:
            cursor = int(body["next_after_id"])
            next_page = client.get(f"/v1/runs/{run_id}/events", params={"after_id": cursor})
            assert next_page.status_code == 200
            assert next_page.json()["events"] == []


def test_audit_replay_endpoint():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with TestClient(create_app()) as client:
        run = client.post(
            f"/v1/opportunities/{req['opportunity_id']}/implement",
            json={"opportunity_id": req["opportunity_id"], "requirement": req},
        )
        assert run.status_code == 200
        run_id = run.json()["run_id"]
        replay = client.get("/v1/audit/replay", params={"run_id": run_id})
        assert replay.status_code == 200
        body = replay.json()
        assert body["run_id"] == run_id
        assert isinstance(body["events"], list)
        if body["events"]:
            assert "event_type" in body["events"][0]


def test_dashboard_overview_and_requeue_endpoints():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with TestClient(create_app()) as client:
        page = client.get("/dashboard")
        assert page.status_code == 200
        assert "Hunter-Craftsman 工作台" in page.text

        run = client.post(
            f"/v1/opportunities/{req['opportunity_id']}/implement",
            json={"opportunity_id": req["opportunity_id"], "requirement": req},
        )
        assert run.status_code == 200
        run_id = run.json()["run_id"]

        release_handoff = client.post("/v1/runs/sync-implement", json={"requirement": req}).json()["release_handoff"]
        release_handoff["release_id"] = f"rel-{release_handoff['run_id']}"
        prepared = client.post("/v1/releases/prepare", json=release_handoff)
        assert prepared.status_code == 200
        release_id = prepared.json()["release_id"]

        overview = client.get("/dashboard/api/overview")
        assert overview.status_code == 200
        body = overview.json()
        assert body["opportunities"] == []
        pipeline = next(item for item in body["pipeline"] if item["technical"]["run_status"] == "implementation_complete")
        assert pipeline["run_id"]
        assert pipeline["stages"]["agent_b"]["status"] == "done"

def test_dashboard_requeue_run_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    with TestClient(create_app()) as client:
        assert api_app._store is not None
        run_id = api_app._store.create_run(
            opportunity_id="opp-requeue",
            revision=1,
            requirement={"opportunity_id": "opp-requeue", "revision": 1, "app": {"name": "Retry"}},
            status="failed",
            phase="failed",
            phase_detail="dead letter",
        )
        api_app._store.enqueue_implementation(run_id, max_attempts=1)
        api_app._store.fail_job(
            run_id,
            error_message="terminal",
            retryable=False,
        )

        resp = client.post(f"/dashboard/api/runs/{run_id}/requeue")
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"


def test_dashboard_requeue_release_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    with TestClient(create_app()) as client:
        assert api_app._store is not None
        release_id = "rel-requeue"
        api_app._store.record_release_policy_check(release_id, passed=True, issues=[])
        api_app._store.upsert_release_state(
            release_id,
            status="failed",
            details={"platform_target": "android", "release_handoff": {"run_id": "run-1"}},
            updated_by="agent_c",
        )
        api_app._store.enqueue_release_submit(release_id, max_attempts=1)
        api_app._store.fail_release_job(
            release_id,
            error_message="terminal",
            retryable=False,
        )

        resp = client.post(f"/dashboard/api/releases/{release_id}/requeue")
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitting"


def test_dashboard_release_approve_and_submit_endpoints(monkeypatch):
    monkeypatch.setattr(settings, "release_require_human_approval", True)
    monkeypatch.setattr(settings, "release_require_policy_checks", True)
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

        approve = client.post(
            f"/dashboard/api/releases/{release_id}/decision",
            json={"approved_by": "ops-user", "decision": "approved", "note": "approved from dashboard"},
        )
        assert approve.status_code == 200
        assert approve.json()["status"] == "approved"

        submit = client.post(f"/dashboard/api/releases/{release_id}/submit")
        assert submit.status_code == 200
        assert submit.json()["status"] == "submitting"


def test_dashboard_release_reject_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "release_require_human_approval", True)
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with TestClient(create_app()) as client:
        sync = client.post("/v1/runs/sync-implement", json={"requirement": req})
        assert sync.status_code == 200
        handoff = dict(sync.json()["release_handoff"])
        release_id = f"rel-{handoff['run_id']}"
        handoff["release_id"] = release_id

        prepare = client.post("/v1/releases/prepare", json=handoff)
        assert prepare.status_code == 200

        reject = client.post(
            f"/dashboard/api/releases/{release_id}/decision",
            json={"approved_by": "ops-user", "decision": "rejected", "note": "reject from dashboard"},
        )
        assert reject.status_code == 200
        assert reject.json()["status"] == "rejected"

        detail = client.get(f"/dashboard/api/releases/{release_id}")
        assert detail.status_code == 200
        assert detail.json()["approval"]["decision"] == "rejected"

import time

import json
from pathlib import Path

from fastapi.testclient import TestClient

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

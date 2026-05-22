import json
from pathlib import Path

from fastapi.testclient import TestClient

from craftsman.api.app import create_app

SAMPLE = Path(__file__).parent.parent / "examples" / "requirement.sample.json"


def test_analyze_endpoint():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    client = TestClient(create_app())
    resp = client.post(f"/v1/opportunities/{req['opportunity_id']}/analyze", json=req)
    assert resp.status_code == 200
    body = resp.json()
    assert body["blueprint"]["accepted"] is True
    assert body["agent_b_status"] == "accepted"


def test_analyze_rejects_incomplete():
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


def test_sync_implement_endpoint():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with TestClient(create_app()) as client:
        resp = client.post("/v1/runs/sync-implement", json={"requirement": req})
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_b_status"] in ("ready_for_release", "submitted")

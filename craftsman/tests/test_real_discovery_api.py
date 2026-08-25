import json
import time

from fastapi.testclient import TestClient

from craftsman.api import app as api_app
from craftsman.api.app import create_app
from craftsman.config import settings


def _play_result(data_quality="mixed", *, opportunity=72, evidence=58, build_fit=82):
    app = {
        "appId": "com.example.timer",
        "title": "Simple Timer",
        "score": 3.6,
        "installs": "100000+",
        "seed_query": "simple timer",
    }
    return {
        "discovery_run_id": "external-disc-id",
        "seed_queries": ["simple timer"],
        "searched_apps": [app],
        "competitor_matrix": [app],
        "low_score_reviews": [],
        "candidate_opportunities": [
            {
                "name": "Focus Timer MVP",
                "niche": "simple timer",
                "target_users": "People who need a quick offline timer",
                "pain_points": ["too many ads", "confusing settings"],
                "competitor_gap": "simpler timer with local history",
                "source_apps": [app],
                "review_pain_summary": [],
                "evidence_score": evidence,
                "opportunity_score": opportunity,
                "build_fit_score": build_fit,
                "decision_reason": "Google Play competitors show demand for a simpler local timer",
            }
        ],
        "data_quality": data_quality,
    }


def _play_result_with_subscription_complaints():
    result = _play_result(data_quality="measured", opportunity=86, evidence=90, build_fit=82)
    candidate = result["candidate_opportunities"][0]
    candidate["pain_points"] = ["subscription complaints", "confusing settings"]
    candidate["competitor_gap"] = "users dislike forced subscriptions and want a local tool"
    candidate["review_pain_summary"] = [
        {
            "app_id": "com.example.timer",
            "theme": "subscription",
            "review_count": 18,
            "frequency_pct": 60,
        }
    ]
    return result




def _play_result_with_events(**kwargs):
    sink = kwargs.get("event_sink")
    if sink:
        sink("checking_environment", "??????????????????", {"seed_query_count": 1})
        sink("searching_query", "????????simple timer", {"query": "simple timer"})
        sink("query_search_complete", "????simple timer??? 1 ???????", {"query": "simple timer", "competitor_count": 1})
        sink("scanning_competitors", "??? 1 ????????????", {"query": "simple timer", "review_target_count": 1})
        sink("reviews_skipped", "????simple timer?????????", {"query": "simple timer"})
        sink("candidate_scored", "????simple timer??????????? 72??? 82??? 58?", {"query": "simple timer"})
    return _play_result()


def _wait_for_status(client, run_id, statuses):
    for _ in range(80):
        resp = client.get(f"/dashboard/api/discovery-runs/{run_id}")
        assert resp.status_code == 200
        status = resp.json()["discovery_run"]["status"]
        if status in statuses:
            return resp.json()
        time.sleep(0.05)
    raise AssertionError(f"discovery run did not reach {statuses}")


def _run_requirement(client, run_id):
    run = client.get(f"/dashboard/api/runs/{run_id}").json()["run"]
    raw = run["requirement_json"]
    return json.loads(raw) if isinstance(raw, str) else raw


def test_discovery_start_creates_real_discovery_only(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr("hunter.discovery.play_monitor.build_play_discovery_run", lambda **kwargs: _play_result())
    with TestClient(create_app()) as client:
        started = client.post("/dashboard/api/discovery-runs", json={"seed_queries": ["simple timer"], "mode": "manual"})
        assert started.status_code == 200
        run_id = started.json()["discovery_run_id"]
        detail = _wait_for_status(client, run_id, {"waiting_for_selection"})
        assert detail["candidates"]
        overview = client.get("/dashboard/api/overview").json()
        assert overview["runs"] == []
        assert overview["pipeline"] == []
        assert overview["opportunities"][0]["candidate_id"] == detail["candidates"][0]["candidate_id"]


def test_play_search_failure_does_not_create_fake_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr("hunter.discovery.play_monitor.build_play_discovery_run", lambda **kwargs: {"searched_apps": [], "candidate_opportunities": [], "data_quality": "assumption"})
    with TestClient(create_app()) as client:
        started = client.post("/dashboard/api/discovery-runs", json={"seed_queries": ["zzzz-no-results"], "mode": "manual"})
        run_id = started.json()["discovery_run_id"]
        detail = _wait_for_status(client, run_id, {"failed"})
        assert detail["candidates"] == []
        overview = client.get("/dashboard/api/overview").json()
        assert overview["opportunities"] == []


def test_manual_candidate_click_creates_b_run(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr("hunter.discovery.play_monitor.build_play_discovery_run", lambda **kwargs: _play_result())
    with TestClient(create_app()) as client:
        started = client.post("/dashboard/api/discovery-runs", json={"seed_queries": ["simple timer"], "mode": "manual"})
        detail = _wait_for_status(client, started.json()["discovery_run_id"], {"waiting_for_selection"})
        candidate_id = detail["candidates"][0]["candidate_id"]
        submit = client.post(f"/dashboard/api/opportunities/{candidate_id}/implement", json={"operator": "tester"})
        assert submit.status_code == 200
        overview = client.get("/dashboard/api/overview").json()
        assert len(overview["runs"]) == 1
        assert overview["opportunities"][0]["submitted_run_id"] == submit.json()["run_id"]
        requirement = _run_requirement(client, submit.json()["run_id"])
        assert requirement.get("automation") is None


def test_auto_mode_requires_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr("hunter.discovery.play_monitor.build_play_discovery_run", lambda **kwargs: _play_result(evidence=40))
    with TestClient(create_app()) as client:
        started = client.post("/dashboard/api/discovery-runs", json={"seed_queries": ["simple timer"], "mode": "auto"})
        _wait_for_status(client, started.json()["discovery_run_id"], {"waiting_for_selection"})
        assert client.get("/dashboard/api/overview").json()["runs"] == []


def test_complex_dependency_check_uses_implementation_scope_only():
    review_only = {
        "niche": "simple timer",
        "pain_points": ["forced subscriptions"],
        "review_pain_summary": [{"theme": "cloud sync problems"}],
        "requirement": {
            "features": [{"title": "Start a local timer", "description": "Run entirely on device."}],
            "budget": {"no_backend": True, "no_login": True, "no_payment": True},
        },
    }
    cloud_product = {
        "niche": "team utility",
        "requirement": {
            "features": [{"title": "Cloud sync", "description": "Keep team data synchronized."}],
            "budget": {"no_backend": True, "no_login": True, "no_payment": True},
        },
    }

    assert api_app._candidate_has_complex_dependency(review_only) is False
    assert api_app._candidate_has_complex_dependency(cloud_product) is True


def test_auto_mode_submits_when_threshold_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr("hunter.discovery.play_monitor.build_play_discovery_run", lambda **kwargs: _play_result())
    with TestClient(create_app()) as client:
        started = client.post("/dashboard/api/discovery-runs", json={"seed_queries": ["simple timer"], "mode": "auto"})
        _wait_for_status(client, started.json()["discovery_run_id"], {"auto_submitted"})
        overview = client.get("/dashboard/api/overview").json()
        assert len(overview["runs"]) == 1
        assert overview["opportunities"][0]["status"] == "submitted_to_b"


def test_auto_publish_ignores_dependency_words_in_review_complaints(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr(
        "hunter.discovery.play_monitor.build_play_discovery_run",
        lambda **kwargs: _play_result_with_subscription_complaints(),
    )
    with TestClient(create_app()) as client:
        started = client.post(
            "/dashboard/api/discovery-runs",
            json={"seed_queries": ["simple timer"], "mode": "auto_publish"},
        )
        detail = _wait_for_status(client, started.json()["discovery_run_id"], {"auto_submitted"})
        run_id = detail["candidates"][0]["submitted_run_id"]
        requirement = _run_requirement(client, run_id)
        assert requirement["automation"]["auto_release"] is True
        descriptions = [feature["description"].lower() for feature in requirement["features"]]
        assert all("subscription" not in description for description in descriptions)


def test_manual_confirmation_inherits_auto_publish_intent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr(
        "hunter.discovery.play_monitor.build_play_discovery_run",
        lambda **kwargs: _play_result(evidence=40),
    )
    with TestClient(create_app()) as client:
        started = client.post(
            "/dashboard/api/discovery-runs",
            json={"seed_queries": ["simple timer"], "mode": "auto_publish"},
        )
        discovery = _wait_for_status(
            client,
            started.json()["discovery_run_id"],
            {"waiting_for_selection"},
        )
        candidate_id = discovery["candidates"][0]["candidate_id"]
        submitted = client.post(
            f"/dashboard/api/opportunities/{candidate_id}/implement",
            json={"operator": "human-reviewer"},
        )
        assert submitted.status_code == 200
        requirement = _run_requirement(client, submitted.json()["run_id"])
        assert requirement["automation"] == {
            "auto_release": True,
            "approved_by": "human-reviewer",
            "release_track": "internal",
        }


def test_overview_exposes_observable_discovery_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr("hunter.discovery.play_monitor.build_play_discovery_run", _play_result_with_events)
    with TestClient(create_app()) as client:
        started = client.post("/dashboard/api/discovery-runs", json={"seed_queries": ["simple timer"], "mode": "manual"})
        run_id = started.json()["discovery_run_id"]
        _wait_for_status(client, run_id, {"waiting_for_selection"})
        overview = client.get("/dashboard/api/overview").json()
        stages = [step["stage"] for step in overview["discovery_progress"]["steps"]]
        event_stages = [event["stage"] for event in overview["discovery_events"]]
        assert "checking_environment" in stages
        assert "searching_play" in stages
        assert "fetching_reviews" in stages
        assert "searching_query" in event_stages
        assert "query_search_complete" in event_stages
        assert overview["discovery_progress"]["metrics"]["competitor_count"] == 1
        assert overview["discovery_progress"]["metrics"]["candidate_count"] >= 1

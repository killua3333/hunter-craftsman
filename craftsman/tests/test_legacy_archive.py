from craftsman.store.db import RunStore
from fastapi.testclient import TestClient

from craftsman.api import app as api_app
from craftsman.api.app import create_app


def test_archive_legacy_demo_runs_includes_sample_but_preserves_real_play_run():
    store = RunStore()
    sample_run = store.create_run(
        "calc-001",
        1,
        {"app": {"name": "Sample Calculator"}},
        status="needs_polish",
    )
    real_run = store.create_run(
        "play-disc-real-tool",
        1,
        {"app": {"name": "Real Tool"}},
        status="implementation_complete",
    )

    assert store.archive_legacy_demo_runs() == 1
    assert store.get_run(sample_run)["archived_at"] is not None
    assert store.get_run(real_run)["archived_at"] is None


def test_dashboard_overview_hides_archived_sample_runs(monkeypatch):
    monkeypatch.setattr(api_app.BackgroundWorker, "start", lambda self: None)
    with TestClient(create_app()) as client:
        assert api_app._store is not None
        sample_run = api_app._store.create_run(
            "calc-001",
            1,
            {"app": {"name": "Sample Calculator"}},
            status="needs_polish",
        )
        real_run = api_app._store.create_run(
            "play-disc-real-tool",
            1,
            {"app": {"name": "Real Tool"}},
            status="implementation_complete",
        )

        response = client.get("/dashboard/api/overview")

        assert response.status_code == 200
        body = response.json()
        assert sample_run not in {item["run_id"] for item in body["pipeline"]}
        assert real_run in {item["run_id"] for item in body["pipeline"]}
        assert sample_run in {item["run_id"] for item in body["archived_runs"]}

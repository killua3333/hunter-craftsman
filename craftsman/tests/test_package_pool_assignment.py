from __future__ import annotations

from craftsman.config import settings
from craftsman.orchestrator.pipeline import _assign_package_from_pool
from craftsman.store.db import RunStore


def test_assign_package_from_pool_overrides_android_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr(settings, "package_pool", "com.pool.one,com.pool.two")
    store = RunStore()
    req = {
        "platform": {"target": "android"},
        "app": {"name": "Generated App", "bundle_id": "com.generated.bad"},
    }

    out = _assign_package_from_pool(store, "run-pool", req)

    assert out["app"]["bundle_id"] == "com.pool.one"
    assert out["app"]["application_id"] == "com.pool.one"


def test_assign_package_from_pool_reuses_existing_run_allocation(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr(settings, "package_pool", "com.pool.one,com.pool.two")
    store = RunStore()
    first = _assign_package_from_pool(
        store,
        "run-pool",
        {"platform": {"target": "android"}, "app": {"name": "A", "bundle_id": "com.bad.a"}},
    )
    second = _assign_package_from_pool(
        store,
        "run-pool",
        {"platform": {"target": "android"}, "app": {"name": "B", "bundle_id": "com.bad.b"}},
    )

    assert first["app"]["bundle_id"] == "com.pool.one"
    assert second["app"]["bundle_id"] == "com.pool.one"


def test_disabled_package_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr(settings, "package_pool", "com.pool.one,com.pool.two")
    store = RunStore()
    store.populate_pool(["com.pool.one", "com.pool.two"])
    store.disable_package("com.pool.one", "package_not_precreated")

    out = _assign_package_from_pool(
        store,
        "run-pool",
        {"platform": {"target": "android"}, "app": {"name": "A", "bundle_id": "com.bad"}},
    )

    assert out["app"]["bundle_id"] == "com.pool.two"

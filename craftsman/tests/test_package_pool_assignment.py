from __future__ import annotations

import pytest

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


def test_package_pool_status_machine_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    store = RunStore()
    store.populate_pool(["com.pool.one", "com.pool.two", "com.pool.three"])
    assert store.mark_package_verified("com.pool.one") is True
    assert store.next_available_package("run-one") == "com.pool.one"
    assert store.disable_package("com.pool.two", "package_not_precreated") is True
    assert store.mark_package_submitted_internal("com.pool.one", "rel-one") is True

    summary = store.package_pool_summary()

    assert summary["submitted_internal"] == 1
    assert summary["invalid"] == 1
    assert summary["available"] == 1
    assert store.release_package("com.pool.one") is False


def test_package_from_pool_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    store = RunStore()
    store.populate_pool(["com.pool.one"])

    assert store.package_is_from_pool("com.pool.one") is True
    assert store.package_is_from_pool("com.generated.bad") is False


def test_assign_package_from_pool_fails_when_pool_exhausted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "runs.db")
    monkeypatch.setattr(settings, "package_pool", "com.pool.one")
    store = RunStore()
    store.populate_pool(["com.pool.one"])
    assert store.next_available_package("other-run") == "com.pool.one"

    with pytest.raises(RuntimeError, match="包名池没有可用包名"):
        _assign_package_from_pool(
            store,
            "run-pool",
            {"platform": {"target": "android"}, "app": {"name": "A", "bundle_id": "com.bad"}},
        )
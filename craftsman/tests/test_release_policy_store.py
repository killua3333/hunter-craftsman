from craftsman.store.db import RunStore


def test_record_and_get_release_policy_check(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    store.record_release_policy_check("rel-1", passed=True, issues=[])
    row = store.get_release_policy_check("rel-1")
    assert row is not None
    assert row["passed"] is True
    assert row["issues"] == []


def test_release_policy_check_upsert(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    store.record_release_policy_check("rel-2", passed=False, issues=["a"])
    store.record_release_policy_check("rel-2", passed=True, issues=[])
    row = store.get_release_policy_check("rel-2")
    assert row is not None
    assert row["passed"] is True
    assert row["issues"] == []

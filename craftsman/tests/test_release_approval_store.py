from craftsman.store.db import RunStore


def test_record_and_get_release_approval(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    store.record_release_approval(
        "release-1",
        decision="approved",
        approved_by="owner",
        note="ok to release",
    )
    row = store.get_release_approval("release-1")
    assert row is not None
    assert row["decision"] == "approved"
    assert row["approved_by"] == "owner"


def test_release_approval_upsert(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    store.record_release_approval("release-2", decision="rejected", approved_by="a", note=None)
    store.record_release_approval("release-2", decision="approved", approved_by="b", note="fixed")
    row = store.get_release_approval("release-2")
    assert row is not None
    assert row["decision"] == "approved"
    assert row["approved_by"] == "b"

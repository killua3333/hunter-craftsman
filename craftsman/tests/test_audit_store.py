from craftsman.store.db import RunStore


def test_append_and_list_audit_logs(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    store.append_audit_log(event_type="run_queued", run_id="run-1", actor="agent_a", payload={"x": 1})
    store.append_audit_log(event_type="run_started", run_id="run-1", actor="worker", payload={"x": 2})
    events = store.list_audit_logs(run_id="run-1", limit=50)
    assert len(events) >= 2
    assert events[0]["event_type"] == "run_queued"
    assert events[-1]["payload"]["x"] == 2


def test_release_state_upsert_and_get(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    store.upsert_release_state("rel-1", status="prepared", details={"a": 1}, updated_by="agent_a")
    store.upsert_release_state("rel-1", status="approved", details={"a": 2}, updated_by="qa")
    row = store.get_release_state("rel-1")
    assert row is not None
    assert row["status"] == "approved"
    assert row["details"]["a"] == 2


def test_sqlite_uses_wal_journal_mode(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    with store._conn() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


def test_repair_release_job_state_reconciles_terminal_jobs(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    release_id = "rel-repair"
    store.record_release_policy_check(release_id, passed=True, issues=[])
    store.upsert_release_state(
        release_id,
        status="dry_run_complete",
        details={"release_handoff": {"release_id": release_id}},
        updated_by="agent_c",
    )
    store.enqueue_release_submit(release_id, max_attempts=3)
    claimed = store.claim_next_release_job(lease_seconds=60, worker_id="worker-test")
    assert claimed is not None
    repaired = store.repair_release_job_state()
    assert repaired == 1
    jobs = store.list_release_jobs(limit=10)
    row = next(item for item in jobs if item["release_id"] == release_id)
    assert row["status"] == "done"


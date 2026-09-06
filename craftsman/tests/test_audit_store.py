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
        status="internal_submitted",
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


def test_event_insert_returns_lastrowid_without_sqlite_returning(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    discovery_id = store.create_discovery_run("disc-1", seed_queries=["timer"], categories=[], mode="manual", operator="tester")
    event_id = store.append_discovery_event(discovery_id, "queued", "queued", {"x": 1})
    audit_id = store.append_audit_log(event_type="queued", run_id="run-1", actor="tester", payload={"x": 1})
    assert event_id > 0
    assert audit_id > 0


def test_production_stages_are_persistent_and_retryable(tmp_path):
    db_path = tmp_path / "runs.db"
    store = RunStore(db_path=db_path)
    run_id = store.create_run("opp-1", 1, {"opportunity_id": "opp-1"})
    stages = [
        {"key": "product_definition", "order": 10, "label": "整理产品方案"},
        {"key": "core_build", "order": 20, "label": "制作核心功能"},
    ]
    store.ensure_production_stages(run_id, stages)
    store.start_production_stage(
        run_id,
        "product_definition",
        user_message="正在整理",
        inputs={"revision": 1},
    )
    store.complete_production_stage(
        run_id,
        "product_definition",
        user_message="产品方案已完成",
        outputs={"artifact": "product_brief.json"},
        acceptance={"passed": True},
    )
    store.start_production_stage(
        run_id,
        "core_build",
        user_message="正在制作",
        inputs={},
    )
    failed_key = store.fail_running_production_stage(
        run_id,
        user_message="本阶段未通过检查",
        acceptance={"passed": False, "reason": "compile_failed"},
    )

    reloaded = RunStore(db_path=db_path)
    rows = reloaded.list_production_stages(run_id)
    assert failed_key == "core_build"
    assert [row["status"] for row in rows] == ["completed", "failed"]
    assert rows[0]["outputs"]["artifact"] == "product_brief.json"
    assert rows[1]["attempt"] == 1

    reloaded.start_production_stage(run_id, "core_build", user_message="重新制作", inputs={})
    retried = reloaded.list_production_stages(run_id)[1]
    assert retried["status"] == "running"
    assert retried["attempt"] == 2

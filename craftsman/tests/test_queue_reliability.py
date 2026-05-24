from craftsman.store.db import RunStore


def test_job_retry_and_dead_letter(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    worker = "worker-a"
    run_id = store.create_run(
        opportunity_id="opp-1",
        revision=1,
        requirement={"opportunity_id": "opp-1", "revision": 1, "app": {"name": "A"}},
    )
    store.enqueue_implementation(run_id, max_attempts=2)

    first = store.claim_next_job(lease_seconds=60, worker_id=worker)
    assert first is not None
    assert first["run_id"] == run_id
    assert store.fail_job(
        run_id,
        error_message="boom-1",
        worker_id=worker,
        lease_token=first["lease_token"],
    ) == "retry"
    row = store.get_job(run_id)
    assert row is not None
    assert row["status"] == "pending"
    assert int(row["attempts"]) == 1

    second = store.claim_next_job(lease_seconds=60, worker_id=worker)
    assert second is not None
    assert second["run_id"] == run_id
    assert store.fail_job(
        run_id,
        error_message="boom-2",
        worker_id=worker,
        lease_token=second["lease_token"],
    ) == "dead_letter"
    final = store.get_job(run_id)
    assert final is not None
    assert final["status"] == "dead_letter"
    assert int(final["attempts"]) == 2


def test_non_retryable_job_goes_dead_letter_immediately(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    worker = "worker-b"
    run_id = store.create_run(
        opportunity_id="opp-2",
        revision=1,
        requirement={"opportunity_id": "opp-2", "revision": 1, "app": {"name": "B"}},
    )
    store.enqueue_implementation(run_id, max_attempts=3)
    claimed = store.claim_next_job(lease_seconds=60, worker_id=worker)
    assert claimed is not None
    assert claimed["run_id"] == run_id
    assert store.fail_job(
        run_id,
        error_message="terminal failure",
        retryable=False,
        worker_id=worker,
        lease_token=claimed["lease_token"],
    ) == "dead_letter"
    final = store.get_job(run_id)
    assert final is not None
    assert final["status"] == "dead_letter"
    assert int(final["attempts"]) == 1


def test_claim_returns_distinct_lease_tokens(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db")
    run_id = store.create_run(
        opportunity_id="opp-3",
        revision=1,
        requirement={"opportunity_id": "opp-3", "revision": 1, "app": {"name": "C"}},
    )
    store.enqueue_implementation(run_id, max_attempts=3)
    first = store.claim_next_job(lease_seconds=1, worker_id="worker-1")
    assert first is not None
    assert store.fail_job(
        run_id,
        error_message="retry once",
        worker_id="worker-1",
        lease_token=first["lease_token"],
    ) == "retry"
    second = store.claim_next_job(lease_seconds=1, worker_id="worker-2")
    assert second is not None
    assert first["lease_token"] != second["lease_token"]

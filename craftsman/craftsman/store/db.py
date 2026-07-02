from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from craftsman.config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_plus_seconds_iso(seconds: int) -> str:
    now = datetime.now(timezone.utc)
    target = now if seconds <= 0 else now + timedelta(seconds=seconds)
    return target.replace(microsecond=0).isoformat()


class RunStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.database_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    phase TEXT,
                    phase_detail TEXT,
                    idempotency_key TEXT,
                    requirement_json TEXT NOT NULL,
                    feedback_json TEXT,
                    workspace_path TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_opp ON runs(opportunity_id, revision);
                CREATE TABLE IF NOT EXISTS job_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    owner_id TEXT,
                    lease_token TEXT,
                    lease_until TEXT,
                    last_error TEXT,
                    dead_letter_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events(run_id, id);
                CREATE TABLE IF NOT EXISTS discovery_runs (
                    discovery_run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'manual',
                    seed_queries_json TEXT NOT NULL,
                    categories_json TEXT NOT NULL,
                    error_message TEXT,
                    operator TEXT,
                    summary_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS discovery_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    discovery_run_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    app_name TEXT NOT NULL,
                    niche TEXT,
                    target_users TEXT,
                    pain_points_json TEXT NOT NULL,
                    competitor_gap TEXT,
                    source_apps_json TEXT NOT NULL,
                    review_pain_summary_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    data_quality TEXT,
                    evidence_score INTEGER,
                    opportunity_score INTEGER,
                    build_fit_score INTEGER,
                    decision_reason TEXT,
                    rejection_reason TEXT,
                    requirement_json TEXT,
                    submitted_run_id TEXT,
                    submitted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_discovery_candidates_run ON discovery_candidates(discovery_run_id, updated_at);
                CREATE TABLE IF NOT EXISTS discovery_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discovery_run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_discovery_events_run ON discovery_events(discovery_run_id, id);
                CREATE TABLE IF NOT EXISTS release_approvals (
                    release_id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    approved_by TEXT NOT NULL,
                    note TEXT,
                    approved_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS release_policy_checks (
                    release_id TEXT PRIMARY KEY,
                    passed INTEGER NOT NULL,
                    issues_json TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS release_states (
                    release_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    details_json TEXT,
                    updated_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    run_id TEXT,
                    release_id TEXT,
                    actor TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_logs_run_id ON audit_logs(run_id, id);
                CREATE INDEX IF NOT EXISTS idx_audit_logs_release_id ON audit_logs(release_id, id);
                CREATE TABLE IF NOT EXISTS release_job_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    release_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    owner_id TEXT,
                    lease_token TEXT,
                    lease_until TEXT,
                    last_error TEXT,
                    dead_letter_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "phase" not in columns:
                conn.execute("ALTER TABLE runs ADD COLUMN phase TEXT")
            if "phase_detail" not in columns:
                conn.execute("ALTER TABLE runs ADD COLUMN phase_detail TEXT")
            if "idempotency_key" not in columns:
                conn.execute("ALTER TABLE runs ADD COLUMN idempotency_key TEXT")
            if "archived_at" not in columns:
                conn.execute("ALTER TABLE runs ADD COLUMN archived_at TEXT")
            if "archive_reason" not in columns:
                conn.execute("ALTER TABLE runs ADD COLUMN archive_reason TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_idempotency ON runs(idempotency_key)")
            queue_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(job_queue)").fetchall()
            }
            if "attempts" not in queue_columns:
                conn.execute("ALTER TABLE job_queue ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
            if "max_attempts" not in queue_columns:
                conn.execute("ALTER TABLE job_queue ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3")
            if "owner_id" not in queue_columns:
                conn.execute("ALTER TABLE job_queue ADD COLUMN owner_id TEXT")
            if "lease_token" not in queue_columns:
                conn.execute("ALTER TABLE job_queue ADD COLUMN lease_token TEXT")
            if "lease_until" not in queue_columns:
                conn.execute("ALTER TABLE job_queue ADD COLUMN lease_until TEXT")
            if "last_error" not in queue_columns:
                conn.execute("ALTER TABLE job_queue ADD COLUMN last_error TEXT")
            if "dead_letter_at" not in queue_columns:
                conn.execute("ALTER TABLE job_queue ADD COLUMN dead_letter_at TEXT")
            if "updated_at" not in queue_columns:
                conn.execute("ALTER TABLE job_queue ADD COLUMN updated_at TEXT")
                conn.execute("UPDATE job_queue SET updated_at = created_at WHERE updated_at IS NULL")

    def enqueue_implementation(self, run_id: str, *, max_attempts: int = 3) -> None:
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO job_queue
                (run_id, status, attempts, max_attempts, owner_id, lease_token, lease_until, last_error, dead_letter_at, created_at, updated_at)
                VALUES (?, 'pending', 0, ?, NULL, NULL, NULL, NULL, NULL, ?, ?)
                """,
                (run_id, max(max_attempts, 1), now, now),
            )

    def claim_next_job(self, *, lease_seconds: int = 300, worker_id: str) -> dict[str, str] | None:
        now = _utc_now_iso()
        lease_until = _utc_plus_seconds_iso(max(lease_seconds, 1))
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT run_id
                FROM job_queue
                WHERE attempts < max_attempts
                  AND (
                    status='pending'
                    OR (status='processing' AND lease_until IS NOT NULL AND lease_until < ?)
                  )
                ORDER BY id
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if not row:
                return None
            run_id = row["run_id"]
            lease_token = str(uuid.uuid4())
            updated = conn.execute(
                """
                UPDATE job_queue
                SET status='processing',
                    attempts=attempts + 1,
                    owner_id=?,
                    lease_token=?,
                    lease_until=?,
                    updated_at=?
                WHERE run_id=?
                  AND attempts < max_attempts
                  AND (
                    status='pending'
                    OR (status='processing' AND lease_until IS NOT NULL AND lease_until < ?)
                  )
                """,
                (worker_id, lease_token, lease_until, now, run_id, now),
            ).rowcount
            if updated != 1:
                return None
            return {"run_id": run_id, "lease_token": lease_token}

    def renew_lease(
        self,
        run_id: str,
        *,
        worker_id: str,
        lease_token: str,
        lease_seconds: int = 300,
    ) -> bool:
        now = _utc_now_iso()
        next_lease = _utc_plus_seconds_iso(max(lease_seconds, 1))
        with self._conn() as conn:
            updated = conn.execute(
                """
                UPDATE job_queue
                SET lease_until=?, updated_at=?
                WHERE run_id=?
                  AND status='processing'
                  AND owner_id=?
                  AND lease_token=?
                """,
                (next_lease, now, run_id, worker_id, lease_token),
            ).rowcount
        return updated == 1

    def complete_job(
        self,
        run_id: str,
        *,
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> str:
        now = _utc_now_iso()
        where = ["run_id=?"]
        values: list[Any] = [now]
        if worker_id is not None and lease_token is not None:
            where.extend(["owner_id=?", "lease_token=?", "status='processing'"])
            values.extend([worker_id, lease_token])
        values.append(run_id)
        with self._conn() as conn:
            updated = conn.execute(
                f"""
                UPDATE job_queue
                SET status='done',
                    owner_id=NULL,
                    lease_token=NULL,
                    lease_until=NULL,
                    updated_at=?
                WHERE {' AND '.join(where)}
                """,
                values,
            ).rowcount
        return "done" if updated == 1 else "stale"

    def fail_job(
        self,
        run_id: str,
        *,
        error_message: str,
        retryable: bool = True,
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> str:
        with self._conn() as conn:
            ownership_clause = ""
            ownership_values: list[Any] = [run_id]
            if worker_id is not None and lease_token is not None:
                ownership_clause = " AND owner_id=? AND lease_token=?"
                ownership_values.extend([worker_id, lease_token])
            row = conn.execute(
                f"SELECT attempts, max_attempts FROM job_queue WHERE run_id=?{ownership_clause}",
                ownership_values,
            ).fetchone()
            if not row:
                return "missing"
            terminal = (not retryable) or int(row["attempts"]) >= int(row["max_attempts"])
            now = _utc_now_iso()
            if terminal:
                conn.execute(
                    """
                    UPDATE job_queue
                    SET status='dead_letter',
                        owner_id=NULL,
                        lease_token=NULL,
                        lease_until=NULL,
                        last_error=?,
                        dead_letter_at=?,
                        updated_at=?
                    WHERE run_id=?
                    """,
                    (error_message, now, now, run_id),
                )
                return "dead_letter"
            conn.execute(
                """
                UPDATE job_queue
                SET status='pending',
                    owner_id=NULL,
                    lease_token=NULL,
                    lease_until=NULL,
                    last_error=?,
                    updated_at=?
                WHERE run_id=?
                """,
                (error_message, now, run_id),
            )
            return "retry"

    def get_job(self, run_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM job_queue WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def enqueue_release_submit(self, release_id: str, *, max_attempts: int = 3) -> None:
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO release_job_queue
                (release_id, status, attempts, max_attempts, owner_id, lease_token, lease_until, last_error, dead_letter_at, created_at, updated_at)
                VALUES (?, 'pending', 0, ?, NULL, NULL, NULL, NULL, NULL, ?, ?)
                """,
                (release_id, max(max_attempts, 1), now, now),
            )

    def claim_next_release_job(self, *, lease_seconds: int = 300, worker_id: str) -> dict[str, str] | None:
        now = _utc_now_iso()
        lease_until = _utc_plus_seconds_iso(max(lease_seconds, 1))
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT release_id
                FROM release_job_queue
                WHERE attempts < max_attempts
                  AND (
                    status='pending'
                    OR (status='processing' AND lease_until IS NOT NULL AND lease_until < ?)
                  )
                ORDER BY id
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if not row:
                return None
            release_id = row["release_id"]
            lease_token = str(uuid.uuid4())
            updated = conn.execute(
                """
                UPDATE release_job_queue
                SET status='processing',
                    attempts=attempts + 1,
                    owner_id=?,
                    lease_token=?,
                    lease_until=?,
                    updated_at=?
                WHERE release_id=?
                  AND attempts < max_attempts
                  AND (
                    status='pending'
                    OR (status='processing' AND lease_until IS NOT NULL AND lease_until < ?)
                  )
                """,
                (worker_id, lease_token, lease_until, now, release_id, now),
            ).rowcount
            if updated != 1:
                return None
            return {"release_id": release_id, "lease_token": lease_token}

    def renew_release_lease(
        self,
        release_id: str,
        *,
        worker_id: str,
        lease_token: str,
        lease_seconds: int = 300,
    ) -> bool:
        now = _utc_now_iso()
        next_lease = _utc_plus_seconds_iso(max(lease_seconds, 1))
        with self._conn() as conn:
            updated = conn.execute(
                """
                UPDATE release_job_queue
                SET lease_until=?, updated_at=?
                WHERE release_id=?
                  AND status='processing'
                  AND owner_id=?
                  AND lease_token=?
                """,
                (next_lease, now, release_id, worker_id, lease_token),
            ).rowcount
        return updated == 1

    def complete_release_job(
        self,
        release_id: str,
        *,
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> str:
        now = _utc_now_iso()
        where = ["release_id=?"]
        where_values: list[Any] = [release_id]
        if worker_id is not None and lease_token is not None:
            where.extend(["owner_id=?", "lease_token=?"])
            where_values.extend([worker_id, lease_token])
        with self._conn() as conn:
            updated = conn.execute(
                f"""
                UPDATE release_job_queue
                SET status='done',
                    owner_id=NULL,
                    lease_token=NULL,
                    lease_until=NULL,
                    updated_at=?
                WHERE {' AND '.join(where)}
                """,
                [now, *where_values],
            ).rowcount
        return "done" if updated == 1 else "stale"

    def fail_release_job(
        self,
        release_id: str,
        *,
        error_message: str,
        retryable: bool = True,
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> str:
        with self._conn() as conn:
            ownership_clause = ""
            ownership_values: list[Any] = [release_id]
            if worker_id is not None and lease_token is not None:
                ownership_clause = " AND owner_id=? AND lease_token=?"
                ownership_values.extend([worker_id, lease_token])
            row = conn.execute(
                f"SELECT attempts, max_attempts FROM release_job_queue WHERE release_id=?{ownership_clause}",
                ownership_values,
            ).fetchone()
            if not row:
                return "missing"
            terminal = (not retryable) or int(row["attempts"]) >= int(row["max_attempts"])
            now = _utc_now_iso()
            if terminal:
                conn.execute(
                    """
                    UPDATE release_job_queue
                    SET status='dead_letter',
                        owner_id=NULL,
                        lease_token=NULL,
                        lease_until=NULL,
                        last_error=?,
                        dead_letter_at=?,
                        updated_at=?
                    WHERE release_id=?
                    """,
                    (error_message, now, now, release_id),
                )
                return "dead_letter"
            conn.execute(
                """
                UPDATE release_job_queue
                SET status='pending',
                    owner_id=NULL,
                    lease_token=NULL,
                    lease_until=NULL,
                    last_error=?,
                    updated_at=?
                WHERE release_id=?
                """,
                (error_message, now, release_id),
            )
            return "retry"

    def create_run(
        self,
        opportunity_id: str,
        revision: int,
        requirement: dict[str, Any],
        status: str = "pending",
        *,
        phase: str | None = None,
        phase_detail: str | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, opportunity_id, revision, status, phase, phase_detail, idempotency_key,
                    requirement_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    opportunity_id,
                    revision,
                    status,
                    phase,
                    phase_detail,
                    idempotency_key,
                    json.dumps(requirement, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return run_id

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        feedback: dict | None = None,
        workspace_path: str | None = None,
        error_message: str | None = None,
        phase: str | None = None,
        phase_detail: str | None = None,
        requirement_json: str | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [_utc_now_iso()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if feedback is not None:
            fields.append("feedback_json = ?")
            values.append(json.dumps(feedback, ensure_ascii=False))
        if workspace_path is not None:
            fields.append("workspace_path = ?")
            values.append(workspace_path)
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        if phase is not None:
            fields.append("phase = ?")
            values.append(phase)
        if phase_detail is not None:
            fields.append("phase_detail = ?")
            values.append(phase_detail)
        if requirement_json is not None:
            fields.append("requirement_json = ?")
            values.append(requirement_json)
        values.append(run_id)
        with self._conn() as conn:
            conn.execute(f"UPDATE runs SET {', '.join(fields)} WHERE run_id = ?", values)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return dict(row)

    def get_latest_run(self, opportunity_id: str, revision: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM runs
                WHERE opportunity_id = ? AND revision = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (opportunity_id, revision),
            ).fetchone()
        return dict(row) if row else None

    def get_run_by_idempotency(self, idempotency_key: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM runs
                WHERE idempotency_key = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (idempotency_key,),
            ).fetchone()
        return dict(row) if row else None

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
        return [dict(row) for row in rows]

    def run_status_counts(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM runs
                GROUP BY status
                """
            ).fetchall()
        return {str(row["status"]): int(row["total"]) for row in rows}

    def append_event(self, run_id: str, phase: str, detail: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO run_events (run_id, phase, detail, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, phase, detail, _utc_now_iso()),
            )

    def list_events(
        self,
        run_id: str,
        *,
        after_id: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, phase, detail, created_at
                FROM run_events
                WHERE run_id = ?
                  AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (run_id, max(after_id, 0), max(limit, 1)),
            ).fetchall()
        return [dict(row) for row in rows]

    def requeue_run(self, run_id: str, *, max_attempts: int | None = None) -> bool:
        now = _utc_now_iso()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT run_id, max_attempts FROM job_queue WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if not existing:
                return False
            next_max_attempts = max_attempts or int(existing["max_attempts"]) or 1
            updated = conn.execute(
                """
                UPDATE job_queue
                SET status='pending',
                    attempts=0,
                    max_attempts=?,
                    owner_id=NULL,
                    lease_token=NULL,
                    lease_until=NULL,
                    last_error=NULL,
                    dead_letter_at=NULL,
                    updated_at=?
                WHERE run_id=?
                """,
                (max(next_max_attempts, 1), now, run_id),
            ).rowcount
            if updated != 1:
                return False
            conn.execute(
                """
                UPDATE runs
                SET status='in_progress',
                    phase='queued',
                    phase_detail='implementation requeued',
                    error_message=NULL,
                    updated_at=?
                WHERE run_id=?
                """,
                (now, run_id),
            )
        return True

    def list_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT q.*, r.opportunity_id, r.revision, r.phase, r.phase_detail, r.status AS run_status
                FROM job_queue q
                JOIN runs r ON r.run_id = q.run_id
                ORDER BY q.updated_at DESC, q.id DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_release_approval(
        self,
        release_id: str,
        *,
        decision: str,
        approved_by: str,
        note: str | None = None,
    ) -> None:
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO release_approvals (
                    release_id, decision, approved_by, note, approved_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(release_id) DO UPDATE SET
                    decision=excluded.decision,
                    approved_by=excluded.approved_by,
                    note=excluded.note,
                    approved_at=excluded.approved_at,
                    updated_at=excluded.updated_at
                """,
                (release_id, decision, approved_by, note, now, now, now),
            )

    def get_release_approval(self, release_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM release_approvals WHERE release_id = ?",
                (release_id,),
            ).fetchone()
        return dict(row) if row else None

    def record_release_policy_check(
        self,
        release_id: str,
        *,
        passed: bool,
        issues: list[str],
    ) -> None:
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO release_policy_checks (
                    release_id, passed, issues_json, checked_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(release_id) DO UPDATE SET
                    passed=excluded.passed,
                    issues_json=excluded.issues_json,
                    checked_at=excluded.checked_at,
                    updated_at=excluded.updated_at
                """,
                (
                    release_id,
                    1 if passed else 0,
                    json.dumps(issues, ensure_ascii=False),
                    now,
                    now,
                    now,
                ),
            )

    def get_release_policy_check(self, release_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM release_policy_checks WHERE release_id = ?",
                (release_id,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["passed"] = bool(data.get("passed"))
        try:
            data["issues"] = json.loads(data.get("issues_json") or "[]")
        except json.JSONDecodeError:
            data["issues"] = []
        return data

    def upsert_release_state(
        self,
        release_id: str,
        *,
        status: str,
        details: dict[str, Any] | None = None,
        updated_by: str | None = None,
    ) -> None:
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO release_states (
                    release_id, status, details_json, updated_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(release_id) DO UPDATE SET
                    status=excluded.status,
                    details_json=excluded.details_json,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """,
                (
                    release_id,
                    status,
                    json.dumps(details or {}, ensure_ascii=False),
                    updated_by,
                    now,
                    now,
                ),
            )

    def get_release_state(self, release_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM release_states WHERE release_id = ?",
                (release_id,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["details"] = json.loads(data.get("details_json") or "{}")
        except json.JSONDecodeError:
            data["details"] = {}
        return data

    def list_release_states(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT rs.*, rp.passed, rp.issues_json, ra.decision, ra.approved_by, ra.note, ra.approved_at
                FROM release_states rs
                LEFT JOIN release_policy_checks rp ON rp.release_id = rs.release_id
                LEFT JOIN release_approvals ra ON ra.release_id = rs.release_id
                ORDER BY rs.updated_at DESC, rs.release_id DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            try:
                data["details"] = json.loads(data.get("details_json") or "{}")
            except json.JSONDecodeError:
                data["details"] = {}
            try:
                data["issues"] = json.loads(data.get("issues_json") or "[]")
            except json.JSONDecodeError:
                data["issues"] = []
            if data.get("passed") is not None:
                data["passed"] = bool(data["passed"])
            out.append(data)
        return out

    def release_status_counts(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM release_states
                GROUP BY status
                """
            ).fetchall()
        return {str(row["status"]): int(row["total"]) for row in rows}

    def requeue_release(self, release_id: str, *, max_attempts: int | None = None) -> bool:
        now = _utc_now_iso()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT release_id, max_attempts FROM release_job_queue WHERE release_id = ?",
                (release_id,),
            ).fetchone()
            if not existing:
                return False
            next_max_attempts = max_attempts or int(existing["max_attempts"]) or 1
            updated = conn.execute(
                """
                UPDATE release_job_queue
                SET status='pending',
                    attempts=0,
                    max_attempts=?,
                    owner_id=NULL,
                    lease_token=NULL,
                    lease_until=NULL,
                    last_error=NULL,
                    dead_letter_at=NULL,
                    updated_at=?
                WHERE release_id=?
                """,
                (max(next_max_attempts, 1), now, release_id),
            ).rowcount
            if updated != 1:
                return False
            conn.execute(
                """
                UPDATE release_states
                SET status='submitting',
                    updated_at=?
                WHERE release_id=?
                """,
                (now, release_id),
            )
        return True

    def list_release_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT q.*, rs.status AS release_status, rs.updated_by
                FROM release_job_queue q
                LEFT JOIN release_states rs ON rs.release_id = q.release_id
                ORDER BY q.updated_at DESC, q.id DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
        return [dict(row) for row in rows]

    def repair_release_job_state(self) -> int:
        """
        Reconcile release jobs that still look processing even though the release
        state is terminal. This can happen after older versions or interrupted
        runs and should never leave the operator console in a contradictory state.
        """
        terminal_statuses = {"published", "dry_run_complete", "failed", "platform_unavailable"}
        now = _utc_now_iso()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT q.release_id, q.status AS job_status, q.owner_id, q.lease_token, rs.status AS release_status
                FROM release_job_queue q
                JOIN release_states rs ON rs.release_id = q.release_id
                WHERE q.status='processing'
                """
            ).fetchall()
            repaired = 0
            for row in rows:
                release_status = str(row["release_status"] or "").strip().lower()
                if release_status not in terminal_statuses:
                    continue
                conn.execute(
                    """
                    UPDATE release_job_queue
                    SET status='done',
                        owner_id=NULL,
                        lease_token=NULL,
                        lease_until=NULL,
                        updated_at=?
                    WHERE release_id=?
                    """,
                    (now, row["release_id"]),
                )
                repaired += 1
        return repaired

    def _decode_json_field(self, data: dict[str, Any], key: str, default: Any) -> None:
        try:
            data[key] = json.loads(data.get(key) or json.dumps(default))
        except (TypeError, json.JSONDecodeError):
            data[key] = default

    def create_discovery_run(
        self,
        discovery_run_id: str,
        *,
        seed_queries: list[str],
        categories: list[str] | None = None,
        mode: str = "manual",
        operator: str | None = None,
    ) -> str:
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO discovery_runs (
                    discovery_run_id, status, mode, seed_queries_json, categories_json,
                    error_message, operator, summary_json, created_at, updated_at
                ) VALUES (?, 'queued', ?, ?, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    discovery_run_id,
                    mode,
                    json.dumps(seed_queries, ensure_ascii=False),
                    json.dumps(categories or [], ensure_ascii=False),
                    operator,
                    json.dumps({}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return discovery_run_id

    def update_discovery_run(
        self,
        discovery_run_id: str,
        *,
        status: str | None = None,
        error_message: str | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [_utc_now_iso()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        if summary is not None:
            fields.append("summary_json = ?")
            values.append(json.dumps(summary, ensure_ascii=False))
        values.append(discovery_run_id)
        with self._conn() as conn:
            conn.execute(f"UPDATE discovery_runs SET {', '.join(fields)} WHERE discovery_run_id = ?", values)

    def get_discovery_run(self, discovery_run_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM discovery_runs WHERE discovery_run_id = ?",
                (discovery_run_id,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        self._decode_json_field(data, "seed_queries_json", [])
        self._decode_json_field(data, "categories_json", [])
        self._decode_json_field(data, "summary_json", {})
        data["seed_queries"] = data.pop("seed_queries_json")
        data["categories"] = data.pop("categories_json")
        data["summary"] = data.pop("summary_json")
        return data

    def list_discovery_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM discovery_runs
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            self._decode_json_field(data, "seed_queries_json", [])
            self._decode_json_field(data, "categories_json", [])
            self._decode_json_field(data, "summary_json", {})
            data["seed_queries"] = data.pop("seed_queries_json")
            data["categories"] = data.pop("categories_json")
            data["summary"] = data.pop("summary_json")
            out.append(data)
        return out

    def append_discovery_event(
        self,
        discovery_run_id: str,
        stage: str,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                INSERT INTO discovery_events (discovery_run_id, stage, message, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    discovery_run_id,
                    stage,
                    message,
                    json.dumps(payload or {}, ensure_ascii=False),
                    _utc_now_iso(),
                ),
            ).fetchone()
        return int(row["id"]) if row else 0

    def list_discovery_events(
        self,
        discovery_run_id: str,
        *,
        after_id: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, discovery_run_id, stage, message, payload_json, created_at
                FROM discovery_events
                WHERE discovery_run_id = ? AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (discovery_run_id, max(after_id, 0), max(limit, 1)),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            self._decode_json_field(data, "payload_json", {})
            data["payload"] = data.pop("payload_json")
            out.append(data)
        return out

    def upsert_discovery_candidate(self, candidate: dict[str, Any]) -> str:
        candidate_id = str(candidate.get("candidate_id") or candidate.get("opportunity_id") or uuid.uuid4())
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO discovery_candidates (
                    candidate_id, discovery_run_id, opportunity_id, status, app_name, niche,
                    target_users, pain_points_json, competitor_gap, source_apps_json,
                    review_pain_summary_json, evidence_json, data_quality, evidence_score,
                    opportunity_score, build_fit_score, decision_reason, rejection_reason,
                    requirement_json, submitted_run_id, submitted_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    status=excluded.status,
                    app_name=excluded.app_name,
                    niche=excluded.niche,
                    target_users=excluded.target_users,
                    pain_points_json=excluded.pain_points_json,
                    competitor_gap=excluded.competitor_gap,
                    source_apps_json=excluded.source_apps_json,
                    review_pain_summary_json=excluded.review_pain_summary_json,
                    evidence_json=excluded.evidence_json,
                    data_quality=excluded.data_quality,
                    evidence_score=excluded.evidence_score,
                    opportunity_score=excluded.opportunity_score,
                    build_fit_score=excluded.build_fit_score,
                    decision_reason=excluded.decision_reason,
                    rejection_reason=excluded.rejection_reason,
                    requirement_json=excluded.requirement_json,
                    updated_at=excluded.updated_at
                """,
                (
                    candidate_id,
                    str(candidate.get("discovery_run_id") or ""),
                    str(candidate.get("opportunity_id") or candidate_id),
                    str(candidate.get("status") or "ready_for_review"),
                    str(candidate.get("app_name") or candidate.get("name") or "Google Play Candidate"),
                    candidate.get("niche"),
                    candidate.get("target_users"),
                    json.dumps(candidate.get("pain_points") or [], ensure_ascii=False),
                    candidate.get("competitor_gap"),
                    json.dumps(candidate.get("source_apps") or [], ensure_ascii=False),
                    json.dumps(candidate.get("review_pain_summary") or [], ensure_ascii=False),
                    json.dumps(candidate.get("evidence") or [], ensure_ascii=False),
                    candidate.get("data_quality"),
                    candidate.get("evidence_score"),
                    candidate.get("opportunity_score"),
                    candidate.get("build_fit_score"),
                    candidate.get("decision_reason"),
                    candidate.get("rejection_reason"),
                    json.dumps(candidate.get("requirement") or {}, ensure_ascii=False),
                    candidate.get("submitted_run_id"),
                    candidate.get("submitted_at"),
                    now,
                    now,
                ),
            )
        return candidate_id

    def get_discovery_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM discovery_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        return self._candidate_from_row(row) if row else None

    def list_discovery_candidates(
        self,
        *,
        discovery_run_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        values: list[Any] = []
        where = ""
        if discovery_run_id:
            where = "WHERE discovery_run_id = ?"
            values.append(discovery_run_id)
        values.append(max(limit, 1))
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM discovery_candidates
                {where}
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    def _candidate_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key, default in (
            ("pain_points_json", []),
            ("source_apps_json", []),
            ("review_pain_summary_json", []),
            ("evidence_json", []),
            ("requirement_json", {}),
        ):
            self._decode_json_field(data, key, default)
        data["pain_points"] = data.pop("pain_points_json")
        data["source_apps"] = data.pop("source_apps_json")
        data["review_pain_summary"] = data.pop("review_pain_summary_json")
        data["evidence"] = data.pop("evidence_json")
        data["requirement"] = data.pop("requirement_json")
        return data

    def mark_discovery_candidate_submitted(self, candidate_id: str, run_id: str) -> bool:
        now = _utc_now_iso()
        with self._conn() as conn:
            updated = conn.execute(
                """
                UPDATE discovery_candidates
                SET status='submitted_to_b', submitted_run_id=?, submitted_at=?, updated_at=?
                WHERE candidate_id=? AND submitted_run_id IS NULL
                """,
                (run_id, now, now, candidate_id),
            ).rowcount
        return updated == 1

    def archive_legacy_demo_runs(self) -> int:
        now = _utc_now_iso()
        patterns = [
            "%QuickScan%",
            "%assumption://autopilot%",
            "%soft fill%",
            "%manual publish smoke%",
        ]
        with self._conn() as conn:
            requirement_clauses = ["requirement_json LIKE ?" for _ in patterns]
            where = "archived_at IS NULL AND (opportunity_id LIKE 'autopilot-%' OR opportunity_id LIKE 'manual-%') AND (" + " OR ".join(requirement_clauses) + ")"
            updated = conn.execute(
                f"""
                UPDATE runs
                SET archived_at=?, archive_reason='legacy demo/fallback discovery archived'
                WHERE {where}
                """,
                [now, *patterns],
            ).rowcount
        return int(updated)
    def append_audit_log(
        self,
        *,
        event_type: str,
        run_id: str | None = None,
        release_id: str | None = None,
        actor: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                INSERT INTO audit_logs (event_type, run_id, release_id, actor, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    event_type,
                    run_id,
                    release_id,
                    actor,
                    json.dumps(payload or {}, ensure_ascii=False),
                    _utc_now_iso(),
                ),
            ).fetchone()
            self._purge_audit_logs(conn)
        return int(row["id"]) if row else 0

    def list_audit_logs(
        self,
        *,
        run_id: str | None = None,
        release_id: str | None = None,
        limit: int | None = None,
        after_id: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["id > ?"]
        values: list[Any] = [max(after_id, 0)]
        if run_id:
            clauses.append("run_id = ?")
            values.append(run_id)
        if release_id:
            clauses.append("release_id = ?")
            values.append(release_id)
        values.append(max(limit or settings.audit_replay_limit, 1))
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT id, event_type, run_id, release_id, actor, payload_json, created_at
                FROM audit_logs
                WHERE {' AND '.join(clauses)}
                ORDER BY id ASC
                LIMIT ?
                """,
                values,
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            try:
                data["payload"] = json.loads(data.get("payload_json") or "{}")
            except json.JSONDecodeError:
                data["payload"] = {}
            out.append(data)
        return out

    def _purge_audit_logs(self, conn: sqlite3.Connection) -> None:
        retention_days = max(settings.audit_retention_days, 1)
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_iso = cutoff.replace(microsecond=0).isoformat()
        conn.execute("DELETE FROM audit_logs WHERE created_at < ?", (cutoff_iso,))

    # ── Package Pool ──────────────────────────────────────────────

    def _ensure_pool_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS package_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                package_name TEXT NOT NULL UNIQUE,
                allocated_to TEXT,
                allocated_at TEXT,
                disabled_reason TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        pool_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(package_pool)").fetchall()
        }
        if "disabled_reason" not in pool_columns:
            conn.execute("ALTER TABLE package_pool ADD COLUMN disabled_reason TEXT")

    def populate_pool(self, package_names: list[str]) -> int:
        """Insert package names into pool if not already present. Returns count."""
        now = _utc_now_iso()
        existing = {r["package_name"] for r in self.list_pool()}
        added = 0
        with self._conn() as conn:
            self._ensure_pool_table(conn)
            for name in package_names:
                if name not in existing:
                    conn.execute(
                        "INSERT OR IGNORE INTO package_pool (package_name, created_at) VALUES (?, ?)",
                        (name, now),
                    )
                    added += 1
        return added

    def next_available_package(self, run_id: str) -> str | None:
        """Pick the first unallocated package, mark it as used by this run."""
        now = _utc_now_iso()
        with self._conn() as conn:
            self._ensure_pool_table(conn)
            row = conn.execute(
                """
                SELECT id, package_name
                FROM package_pool
                WHERE allocated_to IS NULL
                  AND (disabled_reason IS NULL OR disabled_reason = '')
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE package_pool SET allocated_to = ?, allocated_at = ? WHERE id = ?",
                (run_id, now, row["id"]),
            )
            return row["package_name"]

    def list_pool(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            self._ensure_pool_table(conn)
            return [dict(r) for r in conn.execute(
                "SELECT * FROM package_pool ORDER BY id ASC"
            ).fetchall()]

    def release_package(self, package_name: str) -> bool:
        """Free a package back to the pool so it can be re-used."""
        with self._conn() as conn:
            self._ensure_pool_table(conn)
            updated = conn.execute(
                "UPDATE package_pool SET allocated_to = NULL, allocated_at = NULL WHERE package_name = ?",
                (package_name,),
            ).rowcount
            return updated == 1

    def disable_package(self, package_name: str, reason: str) -> bool:
        """Mark a package as unusable until an operator fixes Play Console state."""
        with self._conn() as conn:
            self._ensure_pool_table(conn)
            updated = conn.execute(
                """
                UPDATE package_pool
                SET allocated_to = NULL, allocated_at = NULL, disabled_reason = ?
                WHERE package_name = ?
                """,
                (reason, package_name),
            ).rowcount
            return updated == 1

    def enable_package(self, package_name: str) -> bool:
        with self._conn() as conn:
            self._ensure_pool_table(conn)
            updated = conn.execute(
                "UPDATE package_pool SET disabled_reason = NULL WHERE package_name = ?",
                (package_name,),
            ).rowcount
            return updated == 1

    def release_package_for_run(self, run_id: str) -> int:
        """Free all packages allocated to a given run_id. Returns count freed."""
        with self._conn() as conn:
            self._ensure_pool_table(conn)
            updated = conn.execute(
                "UPDATE package_pool SET allocated_to = NULL, allocated_at = NULL WHERE allocated_to = ?",
                (run_id,),
            ).rowcount
            return updated

    def reset_pool(self) -> int:
        """Free ALL allocated packages. Returns count freed."""
        with self._conn() as conn:
            self._ensure_pool_table(conn)
            updated = conn.execute(
                "UPDATE package_pool SET allocated_to = NULL, allocated_at = NULL WHERE allocated_to IS NOT NULL"
            ).rowcount
            return updated

    def pool_usage_count(self) -> tuple[int, int]:
        """Returns (used, total)."""
        with self._conn() as conn:
            self._ensure_pool_table(conn)
            total = conn.execute("SELECT COUNT(*) AS c FROM package_pool").fetchone()["c"]
            used = conn.execute("SELECT COUNT(*) AS c FROM package_pool WHERE allocated_to IS NOT NULL").fetchone()["c"]
            return used, total

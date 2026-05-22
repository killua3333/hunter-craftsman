from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from craftsman.config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class RunStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.database_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
                    created_at TEXT NOT NULL
                );
                """
            )

    def enqueue_implementation(self, run_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO job_queue (run_id, status, created_at) VALUES (?, 'pending', ?)",
                (run_id, _utc_now_iso()),
            )

    def claim_next_job(self) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT run_id FROM job_queue WHERE status='pending' ORDER BY id LIMIT 1"
            ).fetchone()
            if not row:
                return None
            run_id = row["run_id"]
            conn.execute(
                "UPDATE job_queue SET status='processing' WHERE run_id=?",
                (run_id,),
            )
            return run_id

    def complete_job(self, run_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE job_queue SET status='done' WHERE run_id=?",
                (run_id,),
            )

    def create_run(
        self,
        opportunity_id: str,
        revision: int,
        requirement: dict[str, Any],
        status: str = "pending",
    ) -> str:
        run_id = str(uuid.uuid4())
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, opportunity_id, revision, status,
                    requirement_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    opportunity_id,
                    revision,
                    status,
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

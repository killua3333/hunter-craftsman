"""Persist pipeline metadata + Hunter JSONL events under repo pipeline_runs/."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from hunter.paths import PROJECT_ROOT

REPO_ROOT = PROJECT_ROOT.parent
PIPELINE_RUNS_DIR = REPO_ROOT / "pipeline_runs"
DEFAULT_GATEWAY_URL = os.getenv("DASHBOARD_GATEWAY_URL", "http://127.0.0.1:8800").rstrip("/")

logger = logging.getLogger("hunter.observability")

_lock = threading.RLock()
_active: PipelineRunContext | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dashboard_url(pipeline_id: str) -> str:
    return f"{DEFAULT_GATEWAY_URL}/pipeline/{pipeline_id}"


class PipelineRunContext:
    def __init__(
        self,
        *,
        pipeline_id: str,
        mode: str,
        question: str | None = None,
        base_url: str = "http://127.0.0.1:8791",
    ) -> None:
        self.pipeline_id = pipeline_id
        self.mode = mode
        self.question = question
        self.base_url = base_url
        self.dir = PIPELINE_RUNS_DIR / pipeline_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "hunter.jsonl"
        self.meta_path = self.dir / "meta.json"
        try:
            events_rel = str(self.events_path.relative_to(REPO_ROOT))
        except ValueError:
            events_rel = str(self.events_path)
        self.meta: dict[str, Any] = {
            "pipeline_id": pipeline_id,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "mode": mode,
            "question": question,
            "status": "running",
            "terminal": None,
            "hunter": {"events_file": events_rel},
            "craftsman": {"base_url": base_url, "run_id": None},
            "publisher": {"release_id": None},
        }
        self._write_meta()

    def emit(self, event_type: str, **payload: Any) -> None:
        row = {"ts": _utc_now(), "type": event_type, **payload}
        with _lock:
            try:
                with self.events_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            except OSError as exc:  # noqa: BLE001
                logger.debug("emit failed: %s", exc)

    def set_run_id(self, run_id: str) -> None:
        with _lock:
            self.meta["craftsman"]["run_id"] = run_id
            self.meta["updated_at"] = _utc_now()
            self._write_meta()

    def set_release_id(self, release_id: str) -> None:
        with _lock:
            self.meta["publisher"]["release_id"] = release_id
            self.meta["updated_at"] = _utc_now()
            self._write_meta()

    def finish(self, outcome: dict[str, Any]) -> None:
        feedback = outcome.get("feedback") if isinstance(outcome.get("feedback"), dict) else {}
        run_id = outcome.get("run_id") or feedback.get("run_id")
        if run_id:
            self.set_run_id(str(run_id))
        publish = outcome.get("publish") if isinstance(outcome.get("publish"), dict) else {}
        release_id = publish.get("release_id")
        if release_id:
            self.set_release_id(str(release_id))
        elif isinstance(feedback.get("release_handoff"), dict):
            handoff = feedback["release_handoff"]
            rid = handoff.get("release_id") or (
                f"rel-{run_id}" if run_id else None
            )
            if rid:
                self.set_release_id(str(rid))

        stopped = outcome.get("stopped")
        status = str((feedback or {}).get("agent_b_status") or "")
        if status == "implementation_complete" and not stopped:
            self.meta["status"] = "complete"
        elif stopped or not outcome.get("accepted", True):
            self.meta["status"] = "stopped" if stopped else "failed"
        else:
            self.meta["status"] = "complete" if status == "implementation_complete" else "running"

        self.meta["terminal"] = {
            "accepted": outcome.get("accepted"),
            "stopped": stopped,
            "agent_b_status": status,
            "correlation_id": outcome.get("correlation_id"),
        }
        self.meta["updated_at"] = _utc_now()
        self._write_meta()
        self.emit("pipeline_complete", status=self.meta["status"], terminal=self.meta["terminal"])

    def _write_meta(self) -> None:
        try:
            self.meta_path.write_text(
                json.dumps(self.meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:  # noqa: BLE001
            logger.debug("write meta failed: %s", exc)


def start_pipeline_run(
    *,
    mode: str,
    question: str | None = None,
    base_url: str = "http://127.0.0.1:8791",
) -> PipelineRunContext | None:
    """Start tracking unless HUNTER_PIPELINE_TRACK=0."""
    global _active
    if os.getenv("HUNTER_PIPELINE_TRACK", "1").strip().lower() in {"0", "false", "no"}:
        return None
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    pipeline_id = f"pl-{day}-{uuid4().hex[:8]}"
    with _lock:
        ctx = PipelineRunContext(
            pipeline_id=pipeline_id,
            mode=mode,
            question=question,
            base_url=base_url,
        )
        ctx.emit("pipeline_start", mode=mode, question=question)
        _active = ctx
    return ctx


def get_active_pipeline() -> PipelineRunContext | None:
    with _lock:
        return _active


def finish_pipeline_run(outcome: dict[str, Any]) -> str | None:
    """Finalize active pipeline; return dashboard URL if tracked."""
    global _active
    with _lock:
        ctx = _active
        _active = None
    if ctx is None:
        return None
    ctx.finish(outcome)
    return dashboard_url(ctx.pipeline_id)

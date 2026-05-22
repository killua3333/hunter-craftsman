from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from craftsman.callback import deliver_feedback
from craftsman.config import settings
from craftsman.models import AgentBStatus
from craftsman.orchestrator.pipeline import analyze_requirement, run_implementation
from craftsman.schema_validate import validate_feedback
from craftsman.store.db import RunStore
from craftsman.worker import BackgroundWorker

logger = logging.getLogger(__name__)

_store: RunStore | None = None
_worker: BackgroundWorker | None = None


class SyncImplementBody(BaseModel):
    requirement: dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store, _worker
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    settings.callback_dir.mkdir(parents=True, exist_ok=True)
    _store = RunStore()
    _worker = BackgroundWorker(_store)
    _worker.start()
    yield
    if _worker:
        _worker.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Craftsman Agent B",
        version="0.1.0",
        description="iOS SwiftUI 自动化车间 — Gate + Reflexion + Release",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "craftsman"}

    @app.post("/v1/opportunities/{opportunity_id}/analyze")
    def analyze(opportunity_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("opportunity_id") != opportunity_id:
            raise HTTPException(400, "opportunity_id mismatch")
        feedback = analyze_requirement(body)
        payload = feedback.to_agent_a_dict()
        errs = validate_feedback(payload)
        if errs:
            logger.warning("feedback schema warnings: %s", errs)
        deliver_feedback(feedback)
        return payload

    @app.post("/v1/opportunities/{opportunity_id}/implement")
    def implement(opportunity_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("opportunity_id") != opportunity_id:
            raise HTTPException(400, "opportunity_id mismatch")
        requirement = body.get("requirement") or body
        gate = analyze_requirement(requirement)
        if not gate.blueprint.accepted:
            deliver_feedback(gate)
            raise HTTPException(
                400,
                detail={
                    "message": "requirement not accepted",
                    "feedback": gate.to_agent_a_dict(),
                },
            )

        assert _store is not None
        run_id = _store.create_run(
            opportunity_id=opportunity_id,
            revision=int(requirement.get("revision") or 1),
            requirement=requirement,
            status=AgentBStatus.IN_PROGRESS.value,
        )
        _store.enqueue_implementation(run_id)
        return {
            "run_id": run_id,
            "agent_b_status": AgentBStatus.IN_PROGRESS.value,
            "opportunity_id": opportunity_id,
        }

    @app.get("/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        assert _store is not None
        row = _store.get_run(run_id)
        if not row:
            raise HTTPException(404, "run not found")
        out: dict[str, Any] = {
            "run_id": row["run_id"],
            "opportunity_id": row["opportunity_id"],
            "revision": row["revision"],
            "status": row["status"],
            "workspace_path": row.get("workspace_path"),
            "error_message": row.get("error_message"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if row.get("feedback_json"):
            out["feedback"] = json.loads(row["feedback_json"])
        return out

    @app.post("/v1/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict[str, str]:
        assert _store is not None
        row = _store.get_run(run_id)
        if not row:
            raise HTTPException(404, "run not found")
        _store.update_run(run_id, status="cancelled")
        return {"run_id": run_id, "status": "cancelled"}

    @app.post("/v1/runs/sync-implement")
    def sync_implement(body: SyncImplementBody) -> dict[str, Any]:
        """同机调试：阻塞执行完整流水线（无人值守 worker 仍推荐异步 implement）。"""
        assert _store is not None
        req = body.requirement
        run_id = _store.create_run(
            opportunity_id=req["opportunity_id"],
            revision=int(req.get("revision") or 1),
            requirement=req,
        )
        fb = run_implementation(_store, run_id)
        return fb.to_agent_a_dict()

    return app

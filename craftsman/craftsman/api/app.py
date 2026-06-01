from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from craftsman.callback import deliver_feedback
from craftsman.config import settings
from craftsman.dashboard import dashboard_html
from craftsman.models import AgentBStatus
from craftsman.orchestrator.policy_checks import check_release_compliance_metadata
from craftsman.orchestrator.pipeline import analyze_requirement, run_implementation
from craftsman.schema_validate import validate_feedback, validate_release_handoff
from craftsman.store.db import RunStore
from craftsman.worker import BackgroundWorker

logger = logging.getLogger(__name__)

_store: RunStore | None = None
_worker: BackgroundWorker | None = None


def _readiness_snapshot(store: RunStore | None) -> dict[str, Any]:
    workspace_ok = settings.workspace_root.exists() and settings.workspace_root.is_dir()
    callbacks_ok = settings.callback_dir.exists() and settings.callback_dir.is_dir()
    database_ok = False
    repaired_release_jobs = 0
    if store is not None:
        repaired_release_jobs = store.repair_release_job_state()
        with store._conn() as conn:
            conn.execute("SELECT 1").fetchone()
        database_ok = True
    return {
        "ready": workspace_ok and callbacks_ok and database_ok,
        "workspace_root": str(settings.workspace_root),
        "callback_dir": str(settings.callback_dir),
        "checks": {
            "workspace_ok": workspace_ok,
            "callbacks_ok": callbacks_ok,
            "database_ok": database_ok,
        },
        "repaired_release_jobs": repaired_release_jobs,
    }


class SyncImplementBody(BaseModel):
    requirement: dict[str, Any] = Field(default_factory=dict)


class ReleaseApprovalBody(BaseModel):
    approved_by: str = Field(min_length=1)
    decision: str = Field(default="approved")
    note: str | None = None


class DashboardReleaseActionBody(BaseModel):
    approved_by: str = Field(default="dashboard-operator", min_length=1)
    decision: str = Field(default="approved")
    note: str | None = None


def _supported_contract_versions() -> list[str]:
    versions = [v.strip() for v in settings.contract_supported_versions.split(",") if v.strip()]
    if settings.contract_default_version not in versions:
        versions.append(settings.contract_default_version)
    return versions


def _negotiate_contract_version(x_contract_version: str | None) -> str:
    requested = (x_contract_version or settings.contract_default_version).strip()
    supported = _supported_contract_versions()
    if requested in supported:
        return requested
    raise HTTPException(
        400,
        detail=_error_detail(
            code="contract_version_unsupported",
            message=f"unsupported contract version: {requested}",
            retryable=False,
            details={"requested": requested, "supported": supported},
        ),
    )


def _with_contract(payload: dict[str, Any], contract_version: str) -> dict[str, Any]:
    out = dict(payload)
    out["contract_version"] = contract_version
    return out


def _require_api_token(x_api_token: str | None) -> None:
    expected = settings.resolved_api_token()
    if not expected:
        return
    if x_api_token == expected:
        return
    raise HTTPException(
        401,
        detail=_error_detail(
            code="unauthorized",
            message="invalid api token",
            retryable=False,
        ),
    )


def _error_detail(
    *,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        }
    }
    if details:
        payload["error"]["details"] = details
    return payload


def _release_platform_target(release_handoff: dict[str, Any] | None, *, fallback: str = "android") -> str:
    if isinstance(release_handoff, dict):
        platform = release_handoff.get("platform")
        if isinstance(platform, dict):
            target = str(platform.get("target") or "").strip().lower()
            if target in {"android", "ios"}:
                return target
        provenance = release_handoff.get("build_provenance")
        if isinstance(provenance, dict):
            backend = str(provenance.get("backend") or "").strip().lower()
            if "xcode" in backend or backend == "ios_xcode":
                return "ios"
            if "android" in backend:
                return "android"
    return fallback


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
        description="多平台自动化车间（Android 默认 / iOS 可选）— Gate + Build + Release",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        run_stats: dict[str, Any] = {}
        if _store is not None:
            try:
                readiness = _readiness_snapshot(_store)
                repaired_release_jobs = int(readiness["repaired_release_jobs"])
                if repaired_release_jobs:
                    _store.append_audit_log(
                        event_type="release_jobs_repaired",
                        actor="system",
                        payload={"count": repaired_release_jobs, "source": "health"},
                    )
                with _store._conn() as conn:
                    row = conn.execute("SELECT COUNT(*) AS total FROM runs").fetchone()
                    run_stats["runs_total"] = int(row["total"]) if row else 0
                run_stats["repaired_release_jobs"] = repaired_release_jobs
            except Exception:
                run_stats["runs_total"] = None
        return {
            "status": "ok",
            "service": "craftsman",
            "gate_mode": settings.gate_mode,
            "skip_gradle_build": settings.skip_gradle_build,
            "publisher_dry_run": settings.publisher_dry_run,
            "runs": run_stats,
            "contract": {
                "default_version": settings.contract_default_version,
                "supported_versions": _supported_contract_versions(),
            },
            "capabilities": {
                "async_implement": True,
                "phase_events": True,
                "release_handoff": True,
                "release_handoff_validation": True,
                "release_human_approval_checkpoint": True,
                "agent_c_android_publisher": True,
            },
        }

    @app.get("/readyz")
    def readyz() -> dict[str, Any]:
        return {"service": "craftsman", **_readiness_snapshot(_store)}

    @app.get("/", response_class=HTMLResponse)
    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard_page() -> str:
        return dashboard_html()

    @app.get("/dashboard/api/overview")
    def dashboard_overview(
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        if settings.resolved_api_token():
            _require_api_token(x_api_token)
        assert _store is not None
        readiness = _readiness_snapshot(_store)
        repaired_release_jobs = int(readiness["repaired_release_jobs"])
        if repaired_release_jobs:
            _store.append_audit_log(
                event_type="release_jobs_repaired",
                actor="system",
                payload={"count": repaired_release_jobs, "source": "dashboard_overview"},
            )
        runs = _store.list_runs(limit=100)
        run_jobs = {row["run_id"]: row for row in _store.list_jobs(limit=50)}
        releases = _store.list_release_states(limit=100)
        release_jobs = {row["release_id"]: row for row in _store.list_release_jobs(limit=50)}
        recent_audit = _store.list_audit_logs(limit=40)

        run_payload: list[dict[str, Any]] = []
        for row in runs:
            job = run_jobs.get(row["run_id"])
            run_payload.append(
                {
                    "run_id": row["run_id"],
                    "opportunity_id": row["opportunity_id"],
                    "revision": row["revision"],
                    "status": row["status"],
                    "phase": row.get("phase"),
                    "phase_detail": row.get("phase_detail"),
                    "error_message": row.get("error_message"),
                    "updated_at": row["updated_at"],
                    "created_at": row["created_at"],
                    "workspace_path": row.get("workspace_path"),
                    "job": (
                        {
                            "status": job.get("status"),
                            "attempts": job.get("attempts"),
                            "max_attempts": job.get("max_attempts"),
                            "last_error": job.get("last_error"),
                            "dead_letter_at": job.get("dead_letter_at"),
                        }
                        if job
                        else None
                    ),
                    "can_requeue": bool(job and job.get("status") in {"dead_letter", "done"}),
                }
            )

        release_payload: list[dict[str, Any]] = []
        for row in releases:
            details = row.get("details") if isinstance(row.get("details"), dict) else {}
            agent_c = details.get("agent_c") if isinstance(details, dict) else {}
            job = release_jobs.get(row["release_id"])
            release_payload.append(
                {
                    "release_id": row["release_id"],
                    "status": row["status"],
                    "updated_at": row["updated_at"],
                    "platform_target": details.get("platform_target"),
                    "policy_passed": row.get("passed"),
                    "approval_decision": row.get("decision"),
                    "issues": row.get("issues") or [],
                    "agent_c_status": agent_c.get("agent_c_status") if isinstance(agent_c, dict) else None,
                    "message": details.get("message") if isinstance(details, dict) else None,
                    "job": (
                        {
                            "status": job.get("status"),
                            "attempts": job.get("attempts"),
                            "max_attempts": job.get("max_attempts"),
                            "last_error": job.get("last_error"),
                            "dead_letter_at": job.get("dead_letter_at"),
                        }
                        if job
                        else None
                    ),
                    "can_requeue": bool(job and job.get("status") in {"dead_letter", "done"}),
                }
            )

        dead_letter_runs = sum(1 for row in run_jobs.values() if row.get("status") == "dead_letter")
        dead_letter_releases = sum(1 for row in release_jobs.values() if row.get("status") == "dead_letter")
        return {
            "summary": {
                "service": "craftsman",
                "gate_mode": settings.gate_mode,
                "publisher_dry_run": settings.publisher_dry_run,
                "job_worker_count": settings.job_worker_count,
                "job_lease_seconds": settings.job_lease_seconds,
                "runs_total": len(runs),
                "releases_total": len(releases),
                "dead_letter_runs": dead_letter_runs,
                "dead_letter_releases": dead_letter_releases,
                "repaired_release_jobs": repaired_release_jobs,
                "ready": readiness["ready"],
                "checks": readiness["checks"],
                "run_counts": _store.run_status_counts(),
                "release_counts": _store.release_status_counts(),
            },
            "runs": run_payload,
            "releases": release_payload,
            "audit": recent_audit,
        }

    @app.get("/dashboard/api/runs/{run_id}")
    def dashboard_run_detail(
        run_id: str,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        if settings.resolved_api_token():
            _require_api_token(x_api_token)
        assert _store is not None
        row = _store.get_run(run_id)
        if not row:
            raise HTTPException(
                404,
                detail=_error_detail(code="run_not_found", message="run not found"),
            )
        events = _store.list_events(run_id, limit=500)
        audit = _store.list_audit_logs(run_id=run_id, limit=100)
        return {"run": row, "events": events, "audit": audit}

    @app.get("/dashboard/api/releases/{release_id}")
    def dashboard_release_detail(
        release_id: str,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        if settings.resolved_api_token():
            _require_api_token(x_api_token)
        assert _store is not None
        release = _store.get_release_state(release_id)
        if not release:
            raise HTTPException(
                404,
                detail=_error_detail(code="release_not_found", message="release not found"),
            )
        policy = _store.get_release_policy_check(release_id)
        approval = _store.get_release_approval(release_id)
        audit = _store.list_audit_logs(release_id=release_id, limit=100)
        release_job = next(
            (row for row in _store.list_release_jobs(limit=200) if row.get("release_id") == release_id),
            None,
        )
        return {
            "release": release,
            "policy": policy,
            "approval": approval,
            "job": release_job,
            "audit": audit,
        }

    @app.post("/dashboard/api/runs/{run_id}/requeue")
    def dashboard_requeue_run(
        run_id: str,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        assert _store is not None
        ok = _store.requeue_run(run_id, max_attempts=max(settings.job_retry_limit + 1, 1))
        if not ok:
            raise HTTPException(
                404,
                detail=_error_detail(code="run_not_found", message="run not found"),
            )
        _store.append_event(run_id, "queued", "implementation requeued from dashboard")
        _store.append_audit_log(
            event_type="run_requeued",
            run_id=run_id,
            actor="dashboard",
            payload={"source": "dashboard"},
        )
        return {"accepted": True, "run_id": run_id, "status": "queued"}

    @app.post("/dashboard/api/releases/{release_id}/requeue")
    def dashboard_requeue_release(
        release_id: str,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        assert _store is not None
        ok = _store.requeue_release(release_id, max_attempts=max(settings.job_retry_limit + 1, 1))
        if not ok:
            raise HTTPException(
                404,
                detail=_error_detail(code="release_not_found", message="release not found"),
            )
        _store.append_audit_log(
            event_type="release_requeued",
            release_id=release_id,
            actor="dashboard",
            payload={"source": "dashboard"},
        )
        return {"accepted": True, "release_id": release_id, "status": "submitting"}

    @app.post("/dashboard/api/releases/{release_id}/decision")
    def dashboard_release_decision(
        release_id: str,
        body: DashboardReleaseActionBody,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        assert _store is not None
        if not _store.get_release_state(release_id):
            raise HTTPException(
                404,
                detail=_error_detail(code="release_not_found", message="release not found"),
            )
        decision = body.decision.strip().lower()
        if decision not in {"approved", "rejected"}:
            raise HTTPException(
                400,
                detail=_error_detail(
                    code="invalid_approval_decision",
                    message="decision must be approved or rejected",
                ),
            )
        _store.record_release_approval(
            release_id,
            decision=decision,
            approved_by=body.approved_by.strip(),
            note=body.note,
        )
        existing = _store.get_release_state(release_id) or {}
        details = existing.get("details") if isinstance(existing.get("details"), dict) else {}
        _store.upsert_release_state(
            release_id,
            status="approved" if decision == "approved" else "rejected",
            details={
                **details,
                "decision": decision,
                "approved_by": body.approved_by.strip(),
                "note": body.note,
            },
            updated_by=body.approved_by.strip(),
        )
        _store.append_audit_log(
            event_type="release_approval_recorded",
            release_id=release_id,
            actor=body.approved_by.strip(),
            payload={"decision": decision, "note": body.note, "source": "dashboard"},
        )
        return {
            "accepted": True,
            "release_id": release_id,
            "status": "approved" if decision == "approved" else "rejected",
        }

    @app.post("/dashboard/api/releases/{release_id}/submit")
    def dashboard_submit_release(
        release_id: str,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        assert _store is not None
        policy = _store.get_release_policy_check(release_id)
        if settings.release_require_policy_checks and (not policy or not policy.get("passed")):
            raise HTTPException(
                409,
                detail=_error_detail(
                    code="release_policy_check_failed",
                    message="release submit requires passing policy checks",
                    details={"release_id": release_id, "policy": policy},
                ),
            )
        approval = _store.get_release_approval(release_id)
        if settings.release_require_human_approval and (not approval or approval.get("decision") != "approved"):
            raise HTTPException(
                409,
                detail=_error_detail(
                    code="release_requires_human_approval",
                    message="release submit requires explicit human approval",
                    details={"release_id": release_id, "approval": approval},
                ),
            )
        state = _store.get_release_state(release_id)
        details = (state or {}).get("details") if isinstance((state or {}).get("details"), dict) else {}
        handoff = details.get("release_handoff") if isinstance(details, dict) else None
        if not isinstance(handoff, dict):
            raise HTTPException(
                404,
                detail=_error_detail(
                    code="release_handoff_missing",
                    message="release handoff not found; call /v1/releases/prepare first",
                    details={"release_id": release_id},
                ),
            )
        platform_target = _release_platform_target(handoff, fallback="android")
        _store.upsert_release_state(
            release_id,
            status="submitting",
            details={
                **details,
                "policy": policy,
                "approval": approval,
                "platform_target": platform_target,
                "release_handoff": handoff,
            },
            updated_by="dashboard",
        )
        _store.enqueue_release_submit(release_id, max_attempts=max(settings.job_retry_limit + 1, 1))
        _store.append_audit_log(
            event_type="release_submit_queued",
            release_id=release_id,
            actor="dashboard",
            payload={"platform_target": platform_target, "source": "dashboard"},
        )
        return {"accepted": True, "release_id": release_id, "status": "submitting"}

    @app.post("/v1/opportunities/{opportunity_id}/analyze")
    def analyze(
        opportunity_id: str,
        body: dict[str, Any],
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        if body.get("opportunity_id") != opportunity_id:
            raise HTTPException(
                400,
                detail=_error_detail(
                    code="opportunity_id_mismatch",
                    message="opportunity_id mismatch",
                    details={"path_id": opportunity_id, "body_id": body.get("opportunity_id")},
                ),
            )
        feedback = analyze_requirement(body)
        payload = feedback.to_agent_a_dict()
        errs = validate_feedback(payload)
        if errs:
            logger.warning("feedback schema warnings: %s", errs)
        deliver_feedback(feedback)
        return _with_contract(payload, contract_version)

    @app.post("/v1/opportunities/{opportunity_id}/implement")
    def implement(
        opportunity_id: str,
        body: dict[str, Any],
        x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        if body.get("opportunity_id") != opportunity_id:
            raise HTTPException(
                400,
                detail=_error_detail(
                    code="opportunity_id_mismatch",
                    message="opportunity_id mismatch",
                    details={"path_id": opportunity_id, "body_id": body.get("opportunity_id")},
                ),
            )
        requirement = body.get("requirement") or body
        idempotency_key = x_idempotency_key or f"{opportunity_id}:{int(requirement.get('revision') or 1)}"
        gate = analyze_requirement(requirement)
        if not gate.blueprint.accepted:
            deliver_feedback(gate)
            raise HTTPException(
                400,
                detail=_error_detail(
                    code="requirement_not_accepted",
                    message="requirement not accepted",
                    details={"feedback": gate.to_agent_a_dict()},
                ),
            )

        assert _store is not None
        existing = _store.get_run_by_idempotency(idempotency_key)
        if existing and existing.get("status") in {"pending", "in_progress", "implementation_complete"}:
            return _with_contract({
                "run_id": existing["run_id"],
                "agent_b_status": existing["status"],
                "opportunity_id": existing["opportunity_id"],
                "idempotency_key": idempotency_key,
            }, contract_version)
        run_id = _store.create_run(
            opportunity_id=opportunity_id,
            revision=int(requirement.get("revision") or 1),
            requirement=requirement,
            status=AgentBStatus.IN_PROGRESS.value,
            phase="queued",
            phase_detail="implementation queued",
            idempotency_key=idempotency_key,
        )
        _store.enqueue_implementation(run_id, max_attempts=max(settings.job_retry_limit + 1, 1))
        _store.append_audit_log(
            event_type="run_queued",
            run_id=run_id,
            actor="agent_a",
            payload={"opportunity_id": opportunity_id, "idempotency_key": idempotency_key},
        )
        return _with_contract({
            "run_id": run_id,
            "agent_b_status": AgentBStatus.IN_PROGRESS.value,
            "opportunity_id": opportunity_id,
            "idempotency_key": idempotency_key,
        }, contract_version)

    @app.get("/v1/runs/{run_id}")
    def get_run(
        run_id: str,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        assert _store is not None
        row = _store.get_run(run_id)
        if not row:
            raise HTTPException(
                404,
                detail=_error_detail(code="run_not_found", message="run not found"),
            )
        out: dict[str, Any] = {
            "run_id": row["run_id"],
            "opportunity_id": row["opportunity_id"],
            "revision": row["revision"],
            "status": row["status"],
            "phase": row.get("phase"),
            "phase_detail": row.get("phase_detail"),
            "workspace_path": row.get("workspace_path"),
            "error_message": row.get("error_message"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if row.get("feedback_json"):
            out["feedback"] = json.loads(row["feedback_json"])
        return _with_contract(out, contract_version)

    @app.get("/v1/runs/{run_id}/events")
    def get_run_events(
        run_id: str,
        after_id: int = 0,
        limit: int = 200,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        assert _store is not None
        row = _store.get_run(run_id)
        if not row:
            raise HTTPException(
                404,
                detail=_error_detail(code="run_not_found", message="run not found"),
            )
        events = _store.list_events(run_id, after_id=after_id, limit=limit)
        next_after_id = after_id
        if events:
            next_after_id = int(events[-1]["id"])
        return _with_contract({
            "run_id": run_id,
            "events": events,
            "next_after_id": next_after_id,
        }, contract_version)

    @app.post("/v1/runs/{run_id}/cancel")
    def cancel_run(
        run_id: str,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, str]:
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        assert _store is not None
        row = _store.get_run(run_id)
        if not row:
            raise HTTPException(
                404,
                detail=_error_detail(code="run_not_found", message="run not found"),
            )
        _store.update_run(run_id, status="cancelled")
        return _with_contract({"run_id": run_id, "status": "cancelled"}, contract_version)

    @app.post("/v1/runs/sync-implement")
    def sync_implement(
        body: SyncImplementBody,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        """同机调试：阻塞执行完整流水线（无人值守 worker 仍推荐异步 implement）。"""
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        assert _store is not None
        req = body.requirement
        if not req.get("opportunity_id"):
            raise HTTPException(
                400,
                detail=_error_detail(
                    code="invalid_requirement",
                    message="requirement.opportunity_id is required",
                ),
            )
        run_id = _store.create_run(
            opportunity_id=req["opportunity_id"],
            revision=int(req.get("revision") or 1),
            requirement=req,
            status=AgentBStatus.IN_PROGRESS.value,
            phase="sync_implement",
            phase_detail="running sync implementation",
            idempotency_key=f"{req['opportunity_id']}:{int(req.get('revision') or 1)}:sync",
        )
        _store.append_audit_log(
            event_type="run_sync_started",
            run_id=run_id,
            actor="agent_a",
            payload={"opportunity_id": req["opportunity_id"]},
        )
        fb = run_implementation(_store, run_id)
        _store.append_audit_log(
            event_type="run_sync_completed",
            run_id=run_id,
            actor="craftsman",
            payload={"status": fb.agent_b_status.value},
        )
        return _with_contract(fb.to_agent_a_dict(), contract_version)

    @app.post("/v1/releases/prepare")
    def release_prepare(
        body: dict[str, Any],
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        """Prepare release handoff for Agent C (policy + state)."""
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        policy = check_release_compliance_metadata(body)
        assert _store is not None
        release_id = str(body.get("release_id") or body.get("run_id") or "pending-release")
        _store.record_release_policy_check(
            release_id,
            passed=bool(policy["passed"]),
            issues=list(policy["issues"]),
        )
        _store.upsert_release_state(
            release_id,
            status="prepared",
            details={
                "policy_passed": bool(policy["passed"]),
                "issues": list(policy["issues"]),
                "release_handoff": body,
                "platform_target": _release_platform_target(body),
            },
            updated_by="agent_a",
        )
        _store.append_audit_log(
            event_type="release_prepared",
            release_id=release_id,
            actor="agent_a",
            payload={"policy": policy},
        )
        return _with_contract({
            "accepted": bool(policy["passed"]),
            "release_id": release_id,
            "platform_target": _release_platform_target(body),
            "approval_required": settings.release_require_human_approval,
            "policy": policy,
            "message": "release handoff prepared for Agent C",
            "release_handoff": body,
        }, contract_version)

    @app.post("/v1/releases/validate-handoff")
    def release_validate_handoff(
        body: dict[str, Any],
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        errors = validate_release_handoff(body)
        if errors:
            raise HTTPException(
                400,
                detail=_error_detail(
                    code="invalid_release_handoff",
                    message="release_handoff schema validation failed",
                    details={"errors": errors},
                ),
            )
        return _with_contract({"accepted": True, "errors": []}, contract_version)

    @app.post("/v1/releases/{release_id}/submit")
    def release_submit(
        release_id: str,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        """Submit release to Agent C (Android) or reserved iOS publisher."""
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        assert _store is not None
        policy = _store.get_release_policy_check(release_id)
        if settings.release_require_policy_checks and (not policy or not policy.get("passed")):
            raise HTTPException(
                409,
                detail=_error_detail(
                    code="release_policy_check_failed",
                    message="release submit requires passing policy checks",
                    details={"release_id": release_id, "policy": policy},
                ),
            )
        approval = _store.get_release_approval(release_id)
        if settings.release_require_human_approval:
            if not approval or approval.get("decision") != "approved":
                raise HTTPException(
                    409,
                    detail=_error_detail(
                        code="release_requires_human_approval",
                        message="release submit requires explicit human approval",
                        details={"release_id": release_id, "approval": approval},
                    ),
                )
        state = _store.get_release_state(release_id)
        details = (state or {}).get("details") if isinstance((state or {}).get("details"), dict) else {}
        handoff = details.get("release_handoff") if isinstance(details, dict) else None
        if not isinstance(handoff, dict):
            raise HTTPException(
                404,
                detail=_error_detail(
                    code="release_handoff_missing",
                    message="release handoff not found; call /v1/releases/prepare first",
                    details={"release_id": release_id},
                ),
            )
        platform_target = _release_platform_target(handoff, fallback="android")
        if platform_target != "android":
            _store.upsert_release_state(
                release_id,
                status="platform_unavailable",
                details={
                    "policy": policy,
                    "approval": approval,
                    "platform_target": platform_target,
                    "message": "ios publisher not implemented",
                },
                updated_by="agent_c",
            )
            return _with_contract({
                "release_id": release_id,
                "status": "platform_unavailable",
                "platform_target": platform_target,
                "message": "ios publisher not implemented; use macOS/Xcode release track",
                "policy": policy,
                "approval": approval,
            }, contract_version)

        _store.upsert_release_state(
            release_id,
            status="submitting",
            details={
                "policy": policy,
                "approval": approval,
                "platform_target": platform_target,
                "release_handoff": handoff,
            },
            updated_by="agent_a",
        )
        _store.enqueue_release_submit(
            release_id,
            max_attempts=max(settings.job_retry_limit + 1, 1),
        )
        _store.append_audit_log(
            event_type="release_submit_queued",
            release_id=release_id,
            actor="agent_a",
            payload={"platform_target": platform_target},
        )
        return _with_contract({
            "release_id": release_id,
            "status": "submitting",
            "agent_c_status": "building",
            "platform_target": platform_target,
            "message": "release submit queued; poll GET /v1/releases/{id} for completion",
            "policy": policy,
            "approval": approval,
        }, contract_version)

    @app.get("/v1/releases/{release_id}")
    def release_status(
        release_id: str,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        """Release status including Agent C publish result."""
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        assert _store is not None
        approval = _store.get_release_approval(release_id)
        policy = _store.get_release_policy_check(release_id)
        state = _store.get_release_state(release_id)
        details = (state or {}).get("details") if isinstance((state or {}).get("details"), dict) else {}
        agent_c = details.get("agent_c") if isinstance(details, dict) else None
        agent_c_dict = agent_c if isinstance(agent_c, dict) else {}
        return _with_contract({
            "release_id": release_id,
            "status": state["status"] if state else "not_prepared",
            "message": "release status from Agent C publisher pipeline",
            "platform_target": details.get("platform_target") if isinstance(details, dict) else None,
            "agent_c_status": agent_c_dict.get("agent_c_status"),
            "approval_required": settings.release_require_human_approval,
            "policy_required": settings.release_require_policy_checks,
            "policy": policy,
            "approval": approval,
            "state": state,
            "agent_c": agent_c,
            "play_console_setup_path": agent_c_dict.get("play_console_setup_path"),
            "setup_sheet": agent_c_dict.get("setup_sheet"),
        }, contract_version)

    @app.post("/v1/releases/{release_id}/approve")
    def release_approve(
        release_id: str,
        body: ReleaseApprovalBody,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        decision = body.decision.strip().lower()
        if decision not in {"approved", "rejected"}:
            raise HTTPException(
                400,
                detail=_error_detail(
                    code="invalid_approval_decision",
                    message="decision must be approved or rejected",
                ),
            )
        assert _store is not None
        _store.record_release_approval(
            release_id,
            decision=decision,
            approved_by=body.approved_by.strip(),
            note=body.note,
        )
        existing = _store.get_release_state(release_id)
        prev_details = (existing or {}).get("details") if isinstance((existing or {}).get("details"), dict) else {}
        merged_details = {
            **prev_details,
            "decision": decision,
            "approved_by": body.approved_by.strip(),
            "note": body.note,
        }
        _store.upsert_release_state(
            release_id,
            status="approved" if decision == "approved" else "rejected",
            details=merged_details,
            updated_by=body.approved_by.strip(),
        )
        _store.append_audit_log(
            event_type="release_approval_recorded",
            release_id=release_id,
            actor=body.approved_by.strip(),
            payload={"decision": decision, "note": body.note},
        )
        approval = _store.get_release_approval(release_id)
        return _with_contract(
            {
                "release_id": release_id,
                "approval": approval,
                "status": "approval_recorded",
            },
            contract_version,
        )

    @app.get("/v1/audit/replay")
    def audit_replay(
        run_id: str | None = None,
        release_id: str | None = None,
        after_id: int = 0,
        limit: int = 200,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
        x_contract_version: str | None = Header(default=None, alias="X-Contract-Version"),
    ) -> dict[str, Any]:
        _require_api_token(x_api_token)
        contract_version = _negotiate_contract_version(x_contract_version)
        assert _store is not None
        logs = _store.list_audit_logs(
            run_id=run_id,
            release_id=release_id,
            after_id=after_id,
            limit=limit,
        )
        next_after_id = after_id
        if logs:
            next_after_id = int(logs[-1]["id"])
        return _with_contract(
            {
                "run_id": run_id,
                "release_id": release_id,
                "events": logs,
                "next_after_id": next_after_id,
            },
            contract_version,
        )

    return app

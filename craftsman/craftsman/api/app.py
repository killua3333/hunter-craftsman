from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
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



def _safe_json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _feature_titles(requirement: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in requirement.get("features") or []:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or item.get("id") or "").strip()
            if title:
                out.append(title)
    return out[:5]


def _opportunity_from_run(row: dict[str, Any]) -> dict[str, Any]:
    requirement = _safe_json_obj(row.get("requirement_json"))
    feedback = _safe_json_obj(row.get("feedback_json"))
    blueprint = feedback.get("blueprint") if isinstance(feedback.get("blueprint"), dict) else {}
    meta = requirement.get("opportunity_meta") if isinstance(requirement.get("opportunity_meta"), dict) else {}
    opportunity = {**meta, **blueprint}
    app = requirement.get("app") if isinstance(requirement.get("app"), dict) else {}
    store = requirement.get("store") if isinstance(requirement.get("store"), dict) else {}
    evidence = opportunity.get("evidence") or requirement.get("evidence") or []
    pain_points = opportunity.get("pain_points") or []
    if not pain_points and isinstance(opportunity.get("product_brief"), str):
        pain_points = [line.strip("- *") for line in opportunity["product_brief"].splitlines() if "pain" in line.lower()][:3]
    status = row.get("status") or "unknown"
    return {
        "opportunity_id": row.get("opportunity_id"),
        "run_id": row.get("run_id"),
        "app_name": opportunity.get("app_name") or app.get("name") or "鍘嗗彶浠诲姟",
        "niche": opportunity.get("niche") or "历史任务，暂无细分领域分析",
        "target_users": opportunity.get("target_users") or "鏆傛棤鐢ㄦ埛鐢诲儚",
        "pain_points": pain_points[:3] if isinstance(pain_points, list) else [],
        "competitor_gap": opportunity.get("competitor_gap") or "鏆傛棤绔炲搧缂哄彛鍒嗘瀽",
        "recommended_features": _feature_titles(requirement),
        "monetization": opportunity.get("monetization") or requirement.get("monetization") or "free",
        "price_tier": opportunity.get("price_tier") or requirement.get("price_tier"),
        "data_quality": opportunity.get("data_quality") or requirement.get("data_quality") or "unknown",
        "evidence": evidence if isinstance(evidence, list) else [],
        "evidence_score": opportunity.get("evidence_score"),
        "source_apps": opportunity.get("source_apps") or [],
        "review_pain_summary": opportunity.get("review_pain_summary") or [],
        "discovery_run_id": opportunity.get("discovery_run_id"),
        "scores": {
            "opportunity": opportunity.get("opportunity_score"),
            "build_fit": opportunity.get("build_fit_score"),
        },
        "decision_reason": opportunity.get("decision_reason") or "鍘嗗彶浠诲姟锛屾殏鏃犻€夋嫨鐞嗙敱",
        "rejected_candidates": opportunity.get("rejected_candidates") or [],
        "status": status,
        "phase": row.get("phase"),
        "phase_detail": row.get("phase_detail"),
        "updated_at": row.get("updated_at"),
        "store_subtitle": store.get("subtitle"),
    }

def _build_opportunity_cards(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_opportunity_from_run(row) for row in runs]


def _stage_status(value: str | None, *, done: set[str], failed: set[str]) -> str:
    raw = str(value or "").lower()
    if raw in done:
        return "done"
    if raw in failed or "failed" in raw or raw == "dead_letter":
        return "failed"
    if raw in {"pending", "queued", "in_progress", "submitting", "processing", "prepared", "approved", "needs_polish"}:
        return "running"
    return "waiting"


def _build_pipeline_items(
    runs: list[dict[str, Any]],
    releases: list[dict[str, Any]],
    run_jobs: dict[str, dict[str, Any]],
    release_jobs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    releases_by_run: dict[str, dict[str, Any]] = {}
    for release in releases:
        details = release.get("details") if isinstance(release.get("details"), dict) else {}
        handoff = details.get("release_handoff") if isinstance(details.get("release_handoff"), dict) else {}
        rid = str(handoff.get("run_id") or "")
        if rid:
            releases_by_run[rid] = release
    items: list[dict[str, Any]] = []
    for row in runs:
        run_id = str(row.get("run_id") or "")
        release = releases_by_run.get(run_id)
        release_details = release.get("details") if isinstance((release or {}).get("details"), dict) else {}
        agent_c = release_details.get("agent_c") if isinstance(release_details.get("agent_c"), dict) else {}
        run_status = str(row.get("status") or "")
        feedback = _safe_json_obj(row.get("feedback_json"))
        quality_report = feedback.get("quality_report") if isinstance(feedback.get("quality_report"), dict) else {}
        release_status = str((release or {}).get("status") or "")
        run_job = run_jobs.get(run_id) or {}
        release_job = release_jobs.get(str((release or {}).get("release_id") or "")) or {}
        items.append({
            "id": run_id,
            "run_id": run_id,
            "release_id": (release or {}).get("release_id"),
            "title": _opportunity_from_run(row)["app_name"],
            "updated_at": (release or row).get("updated_at"),
            "stages": {
                "agent_a": {
                    "label": "发现需求",
                    "status": "done" if row.get("opportunity_id") else "waiting",
                    "detail": "闇€姹傚凡杩涘叆鐢熸垚闃熷垪" if row.get("opportunity_id") else "绛夊緟 Agent A",
                },
                "agent_b": {
                    "label": "鐢熸垚 App",
                    "status": _stage_status(run_status, done={"implementation_complete"}, failed={"failed", "implementation_failed"}),
                    "detail": row.get("phase_detail") or run_job.get("last_error") or run_status,
                    "can_requeue": bool(run_job.get("status") in {"dead_letter", "done"}),
                    "quality_report": quality_report,
                    "quality_score": quality_report.get("quality_score") or feedback.get("quality_score"),
                    "release_ready": quality_report.get("release_ready") if quality_report else feedback.get("release_ready"),
                },
                "agent_c": {
                    "label": "鍐呴儴娴嬭瘯涓婃灦",
                    "status": _stage_status(release_status, done={"published", "dry_run_complete", "internal_submitted"}, failed={"failed", "needs_manual_action"}),
                    "detail": agent_c.get("operator_action") or release_details.get("message") or agent_c.get("agent_c_status") or release_status or "绛夊緟鍙戝竷浜ゆ帴",
                    "track": agent_c.get("track") or release_details.get("track") or settings.android_release_track,
                    "can_requeue": bool(release_job.get("status") in {"dead_letter", "done"}),
                },
            },
            "technical": {
                "run_status": run_status,
                "release_status": release_status,
                "run_job": run_job,
                "release_job": release_job,
            },
        })
    return items


def _latest_item(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
    for item in items:
        if item.get(key):
            return item
    return {}


DISCOVERY_STAGE_ORDER = [
    ("checking_environment", "\u51c6\u5907\u91c7\u96c6"),
    ("searching_play", "\u641c\u7d22\u5e94\u7528"),
    ("scanning_competitors", "\u5206\u6790\u7ade\u54c1"),
    ("fetching_reviews", "\u8bfb\u53d6\u8bc4\u8bba"),
    ("scoring_candidates", "\u5019\u9009\u8bc4\u5206"),
    ("waiting_for_selection", "\u7b49\u5f85\u9009\u62e9"),
]

DISCOVERY_STAGE_ALIASES = {
    "checking_environment": "checking_environment",
    "play_tools_loaded": "checking_environment",
    "searching_query": "searching_play",
    "query_search_complete": "searching_play",
    "query_search_failed": "searching_play",
    "query_no_competitors": "searching_play",
    "scanning_competitors": "scanning_competitors",
    "fetching_reviews": "fetching_reviews",
    "reviews_complete": "fetching_reviews",
    "reviews_skipped": "fetching_reviews",
    "review_fetch_failed": "fetching_reviews",
    "candidate_scored": "scoring_candidates",
    "scoring_candidates": "scoring_candidates",
    "candidate_saved": "scoring_candidates",
    "candidate_rejected": "scoring_candidates",
    "waiting_for_selection": "waiting_for_selection",
    "auto_submitted": "waiting_for_selection",
    "failed": "failed",
}


def _discovery_progress_payload(run: dict[str, Any] | None, events: list[dict[str, Any]]) -> dict[str, Any]:
    if not run:
        return {"steps": [], "metrics": {}, "current_stage": None}
    status = str(run.get("status") or "queued")
    seen: set[str] = set()
    metrics = {
        "searched_query_count": 0,
        "competitor_count": 0,
        "review_group_count": 0,
        "low_score_review_count": 0,
        "candidate_count": 0,
    }
    failed_stage = None
    for event in events:
        stage = DISCOVERY_STAGE_ALIASES.get(str(event.get("stage") or ""))
        if stage:
            seen.add(stage)
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
        for key in metrics:
            if key in progress:
                try:
                    metrics[key] = max(metrics[key], int(progress.get(key) or 0))
                except (TypeError, ValueError):
                    pass
        if not progress and event.get("stage") == "query_search_complete":
            metrics["competitor_count"] += int(payload.get("competitor_count") or 0)
        if not progress and event.get("stage") == "reviews_complete":
            metrics["review_group_count"] += 1
            metrics["low_score_review_count"] += int(payload.get("low_score_review_count") or 0)
        if event.get("stage") == "failed":
            failed_stage = stage or "failed"
    summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
    summary_progress = summary.get("progress") if isinstance(summary.get("progress"), dict) else {}
    for key in metrics:
        if key in summary_progress:
            try:
                metrics[key] = max(metrics[key], int(summary_progress.get(key) or 0))
            except (TypeError, ValueError):
                pass
    current_stage = DISCOVERY_STAGE_ALIASES.get(status) or status
    steps = []
    reached_current = False
    for stage, label in DISCOVERY_STAGE_ORDER:
        if status == "failed" and not reached_current and stage not in seen:
            step_status = "waiting"
        elif status in {"waiting_for_selection", "auto_submitted"} and stage in seen | {"waiting_for_selection"}:
            step_status = "done"
        elif status == "failed" and (stage == failed_stage or (not failed_stage and stage == current_stage)):
            step_status = "failed"
        elif stage == current_stage and status not in {"waiting_for_selection", "auto_submitted", "failed"}:
            step_status = "running"
            reached_current = True
        elif stage in seen:
            step_status = "done"
        else:
            step_status = "waiting"
        steps.append({"stage": stage, "label": label, "status": step_status})
    if status == "failed" and steps and not any(step["status"] == "failed" for step in steps):
        for step in reversed(steps):
            if step["status"] in {"running", "done"}:
                step["status"] = "failed"
                break
    return {"steps": steps, "metrics": metrics, "current_stage": current_stage}


def _build_agent_status(
    runs: list[dict[str, Any]],
    releases: list[dict[str, Any]],
    run_jobs: dict[str, dict[str, Any]],
    release_jobs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    latest_run = runs[0] if runs else {}
    latest_release = releases[0] if releases else {}
    run_job = run_jobs.get(str(latest_run.get("run_id") or "")) or {}
    release_job = release_jobs.get(str(latest_release.get("release_id") or "")) or {}
    return {
        "agent_a": {
            "status": "ready" if latest_run else "idle",
            "current_step": latest_run.get("opportunity_id") or "绛夊緟鍚姩鏈轰細鍙戠幇",
            "last_error": None,
            "updated_at": latest_run.get("updated_at"),
        },
        "agent_b": {
            "status": latest_run.get("status") or "idle",
            "current_step": latest_run.get("phase_detail") or latest_run.get("phase") or "绛夊緟鐢熸垚浠诲姟",
            "last_error": latest_run.get("error_message") or run_job.get("last_error"),
            "updated_at": latest_run.get("updated_at"),
        },
        "agent_c": {
            "status": latest_release.get("status") or "idle",
            "current_step": "Google Play internal track" if latest_release else "绛夊緟鍙戝竷浠诲姟",
            "last_error": release_job.get("last_error"),
            "updated_at": latest_release.get("updated_at"),
        },
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


class DiscoveryStartBody(BaseModel):
    seed_queries: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    mode: str = Field(default="manual")
    operator: str | None = None
    competitors_per_query: int = Field(default=5, ge=1, le=20)
    reviews_per_app: int = Field(default=30, ge=0, le=200)


class OpportunityImplementBody(BaseModel):
    operator: str = Field(default="dashboard-operator")

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


def _release_quality_blocker(handoff: dict[str, Any]) -> dict[str, Any] | None:
    score = handoff.get("quality_score")
    report = handoff.get("quality_report") if isinstance(handoff.get("quality_report"), dict) else {}
    if score is None:
        score = report.get("quality_score")
    release_ready = handoff.get("release_ready")
    if release_ready is None:
        release_ready = report.get("release_ready")
    if score is None:
        return None
    try:
        score_int = int(score)
    except (TypeError, ValueError):
        score_int = 0
    if bool(release_ready) and score_int >= 75:
        return None
    return {
        "quality_score": score_int,
        "release_ready": bool(release_ready),
        "failure_classes": report.get("failure_classes") or [],
        "operator_action": "App 质量分未达到 75，需要继续修复或人工确认后再发布。",
    }


def _build_discovery_runs(runs: list[dict[str, Any]], audit: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in runs:
        requirement = _safe_json_obj(row.get("requirement_json"))
        meta = requirement.get("opportunity_meta") if isinstance(requirement.get("opportunity_meta"), dict) else {}
        run_id = meta.get("discovery_run_id")
        if run_id and run_id not in seen:
            seen.add(str(run_id))
            out.append({
                "discovery_run_id": run_id,
                "updated_at": row.get("updated_at"),
                "final_selected_opportunity": _opportunity_from_run(row),
                "source_apps": meta.get("source_apps") or [],
                "review_pain_summary": meta.get("review_pain_summary") or [],
                "seed_queries": meta.get("seed_queries") or [],
                "candidate_opportunities": meta.get("candidate_opportunities") or [],
                "rejected_candidates": meta.get("rejected_candidates") or [],
            })
    for event in audit:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        discovery = payload.get("discovery_run") if isinstance(payload.get("discovery_run"), dict) else {}
        run_id = discovery.get("discovery_run_id")
        if run_id and run_id not in seen:
            seen.add(str(run_id))
            out.append(discovery)
    return out[:20]


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    parts = [p for p in cleaned.split("-") if p]
    return "-".join(parts)[:48] or "play-candidate"


def _candidate_payload(discovery_run_id: str, raw: dict[str, Any], *, data_quality: str) -> dict[str, Any]:
    base_id = _slug(str(raw.get("name") or raw.get("niche") or "candidate"))
    candidate_id = f"{discovery_run_id}-{base_id}"[:96]
    source_apps = raw.get("source_apps") if isinstance(raw.get("source_apps"), list) else []
    review_pain_summary = raw.get("review_pain_summary") if isinstance(raw.get("review_pain_summary"), list) else []
    evidence = []
    for app in source_apps[:5]:
        if isinstance(app, dict):
            evidence.append({
                "source": "google_play",
                "app_id": app.get("appId") or app.get("app_id"),
                "title": app.get("title"),
                "score": app.get("score"),
                "installs": app.get("installs"),
                "seed_query": app.get("seed_query"),
            })
    for pain in review_pain_summary[:5]:
        if isinstance(pain, dict):
            evidence.append({
                "source": "google_play_review_cluster",
                "app_id": pain.get("app_id"),
                "theme": pain.get("theme"),
                "review_count": pain.get("review_count"),
                "frequency_pct": pain.get("frequency_pct"),
            })
    return {
        "candidate_id": candidate_id,
        "discovery_run_id": discovery_run_id,
        "opportunity_id": f"play-{candidate_id}",
        "status": "ready_for_review",
        "app_name": raw.get("app_name") or raw.get("name") or "Google Play Opportunity",
        "niche": raw.get("niche"),
        "target_users": raw.get("target_users"),
        "pain_points": raw.get("pain_points") if isinstance(raw.get("pain_points"), list) else [],
        "competitor_gap": raw.get("competitor_gap"),
        "source_apps": source_apps,
        "review_pain_summary": review_pain_summary,
        "evidence": evidence,
        "data_quality": data_quality,
        "evidence_score": int(raw.get("evidence_score") or 0),
        "opportunity_score": int(raw.get("opportunity_score") or 0),
        "build_fit_score": int(raw.get("build_fit_score") or 0),
        "decision_reason": raw.get("decision_reason") or "来自 Google Play 搜索、竞品详情和低分评论证据。",
        "rejection_reason": raw.get("rejection_reason"),
    }


def _candidate_has_complex_dependency(candidate: dict[str, Any]) -> bool:
    fields = [
        candidate.get("niche"),
        candidate.get("target_users"),
        candidate.get("competitor_gap"),
        candidate.get("decision_reason"),
        candidate.get("pain_points"),
        candidate.get("review_pain_summary"),
    ]
    text = json.dumps(fields, ensure_ascii=False).lower()
    blockers = (
        "account", "login", "sign in", "subscription", "payment",
        "backend", "server", "cloud sync", "real-time sync",
        "账号", "登录", "支付", "订阅", "服务器", "云同步",
    )
    return any(token in text for token in blockers)


def _passes_auto_discovery_threshold(candidate: dict[str, Any]) -> bool:
    return (
        candidate.get("data_quality") in {"mixed", "measured"}
        and int(candidate.get("evidence_score") or 0) >= 55
        and int(candidate.get("build_fit_score") or 0) >= 70
        and int(candidate.get("opportunity_score") or 0) >= 60
        and not _candidate_has_complex_dependency(candidate)
    )


def _features_for_candidate(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    niche = str(candidate.get("niche") or candidate.get("app_name") or "").lower()
    pain_text = ", ".join(str(p) for p in (candidate.get("pain_points") or [])[:3])

    presets: list[tuple[tuple[str, ...], list[tuple[str, str]]]] = [
        (("checklist", "todo", "to do", "task"), [
            ("Add checklist items", "Create simple local checklist items with a title and optional note."),
            ("Mark items complete", "Check off finished items and keep unfinished items visible."),
            ("Review today's list", "Show an empty state, active list, and completed section."),
        ]),
        (("timer", "stopwatch", "pomodoro"), [
            ("Start a focused timer", "Set minutes locally and start, pause, or reset the timer."),
            ("Save timer presets", "Keep frequently used durations on device."),
            ("Show session history", "Record recently completed sessions locally."),
        ]),
        (("converter", "unit"), [
            ("Convert units", "Enter a value and choose source and target units."),
            ("Switch common units", "Offer a small set of practical conversion categories."),
            ("Remember recent conversions", "Keep recent inputs locally for quick reuse."),
        ]),
        (("habit", "tracker"), [
            ("Track daily habits", "Create habits and mark today's completion."),
            ("Show streaks", "Calculate simple local streak counts."),
            ("Review habit history", "Show recent completion state without accounts or sync."),
        ]),
        (("expense", "budget"), [
            ("Record an expense", "Add amount, category, and note locally."),
            ("View spending summary", "Show totals by day or category."),
            ("Edit recent records", "Update or remove local expense entries."),
        ]),
        (("water", "reminder"), [
            ("Log water intake", "Record cups or milliliters consumed today."),
            ("Set daily goal", "Keep a local hydration target."),
            ("Show progress", "Display today's progress and remaining amount."),
        ]),
    ]
    selected: list[tuple[str, str]] | None = None
    for keys, features in presets:
        if any(key in niche for key in keys):
            selected = features
            break
    if selected is None:
        selected = [
            ("Create a local record", "Capture the main input for this tool without login or sync."),
            ("Review saved records", "Show current and previous local entries clearly."),
            ("Edit or clear data", "Let users adjust local state safely."),
        ]

    result = []
    for idx, (title, description) in enumerate(selected[:3], start=1):
        result.append({
            "id": f"feature_{idx}",
            "type": "local_tool",
            "title": title,
            "description": f"{description} Evidence pain points to avoid: {pain_text or 'unclear value proposition'}." ,
        })
    return result

def _requirement_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    app_name = str(candidate.get("app_name") or "Play Opportunity MVP")
    slug = _slug(app_name).replace("-", "")[:32] or "playmvp"
    pains = candidate.get("pain_points") if isinstance(candidate.get("pain_points"), list) else []
    source_apps = candidate.get("source_apps") if isinstance(candidate.get("source_apps"), list) else []
    review_summary = candidate.get("review_pain_summary") if isinstance(candidate.get("review_pain_summary"), list) else []
    features = _features_for_candidate(candidate)
    meta = {
        "discovery_run_id": candidate.get("discovery_run_id"),
        "candidate_id": candidate.get("candidate_id"),
        "niche": candidate.get("niche"),
        "target_users": candidate.get("target_users"),
        "pain_points": pains,
        "competitor_gap": candidate.get("competitor_gap"),
        "source_apps": source_apps,
        "review_pain_summary": review_summary,
        "evidence_score": candidate.get("evidence_score"),
        "opportunity_score": candidate.get("opportunity_score"),
        "build_fit_score": candidate.get("build_fit_score"),
        "decision_reason": candidate.get("decision_reason"),
        "data_quality": candidate.get("data_quality"),
    }
    return {
        "schema_version": settings.contract_default_version,
        "opportunity_id": candidate.get("opportunity_id") or candidate.get("candidate_id"),
        "revision": 1,
        "platform": {"target": "android"},
        "app": {
            "name": app_name,
            "bundle_id": f"com.huntercraftsman.{slug}",
            "application_id": f"com.huntercraftsman.{slug}",
        },
        "data_quality": candidate.get("data_quality"),
        "evidence": candidate.get("evidence") or [],
        "features": features,
        "core_logic": {
            "primary_flow": features[0]["title"] if features else "Local main flow",
            "persistence": "SharedPreferences",
            "offline_first": True,
        },
        "ui_layout": {"navigation": "single", "states": ["empty", "input", "result", "history"]},
        "store": {
            "subtitle": f"面向{candidate.get('niche') or '细分工具'}的简洁本地工具",
            "description": candidate.get("decision_reason") or "基于 Google Play 竞品和低分评论发现的本地优先工具。",
            "keywords": [str(candidate.get("niche") or "utility"), "offline", "simple"],
            "privacy_url": "https://example.com/privacy",
        },
        "budget": {"max_core_features": 3, "no_backend": True, "no_login": True, "no_payment": True},
        "opportunity_meta": meta,
    }


def _opportunity_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "opportunity_id": candidate.get("opportunity_id"),
        "run_id": candidate.get("submitted_run_id"),
        "discovery_run_id": candidate.get("discovery_run_id"),
        "app_name": candidate.get("app_name"),
        "niche": candidate.get("niche"),
        "target_users": candidate.get("target_users"),
        "pain_points": candidate.get("pain_points") or [],
        "competitor_gap": candidate.get("competitor_gap"),
        "recommended_features": [f.get("title") for f in (candidate.get("requirement") or {}).get("features", []) if isinstance(f, dict)],
        "data_quality": candidate.get("data_quality"),
        "evidence": candidate.get("evidence") or [],
        "evidence_score": candidate.get("evidence_score"),
        "source_apps": candidate.get("source_apps") or [],
        "review_pain_summary": candidate.get("review_pain_summary") or [],
        "scores": {
            "opportunity": candidate.get("opportunity_score"),
            "build_fit": candidate.get("build_fit_score"),
        },
        "decision_reason": candidate.get("decision_reason"),
        "status": candidate.get("status"),
        "submitted_run_id": candidate.get("submitted_run_id"),
        "updated_at": candidate.get("updated_at"),
    }


def _submit_candidate_to_b(store: RunStore, candidate_id: str, *, actor: str = "dashboard") -> dict[str, Any]:
    candidate = store.get_discovery_candidate(candidate_id)
    if not candidate:
        raise HTTPException(404, detail=_error_detail(code="candidate_not_found", message="opportunity candidate not found"))
    if candidate.get("submitted_run_id"):
        return {"accepted": True, "candidate_id": candidate_id, "run_id": candidate.get("submitted_run_id"), "status": "already_submitted"}
    requirement = candidate.get("requirement") if isinstance(candidate.get("requirement"), dict) and candidate.get("requirement") else _requirement_from_candidate(candidate)
    gate = analyze_requirement(requirement)
    if not gate.blueprint.accepted:
        raise HTTPException(
            400,
            detail=_error_detail(
                code="candidate_requirement_not_accepted",
                message="candidate requirement did not pass Agent B gate",
                details={"feedback": gate.to_agent_a_dict()},
            ),
        )
    opportunity_id = str(requirement.get("opportunity_id") or candidate.get("opportunity_id") or candidate_id)
    idempotency_key = f"candidate:{candidate_id}:implementation"
    existing = store.get_run_by_idempotency(idempotency_key)
    if existing:
        store.mark_discovery_candidate_submitted(candidate_id, existing["run_id"])
        return {"accepted": True, "candidate_id": candidate_id, "run_id": existing["run_id"], "status": existing.get("status")}
    run_id = store.create_run(
        opportunity_id=opportunity_id,
        revision=int(requirement.get("revision") or 1),
        requirement=requirement,
        status=AgentBStatus.IN_PROGRESS.value,
        phase="queued",
        phase_detail="implementation queued from Play discovery candidate",
        idempotency_key=idempotency_key,
    )
    store.enqueue_implementation(run_id, max_attempts=max(settings.job_retry_limit + 1, 1))
    store.mark_discovery_candidate_submitted(candidate_id, run_id)
    store.append_audit_log(
        event_type="discovery_candidate_submitted_to_b",
        run_id=run_id,
        actor=actor,
        payload={"candidate_id": candidate_id, "opportunity_id": opportunity_id},
    )
    return {"accepted": True, "candidate_id": candidate_id, "run_id": run_id, "status": "queued"}


def _discovery_status_for_stage(stage: str) -> str | None:
    if stage == "checking_environment":
        return "checking_environment"
    if stage in {"play_tools_loaded", "searching_query", "query_search_complete", "query_search_failed", "query_no_competitors"}:
        return "searching_play"
    if stage == "scanning_competitors":
        return "scanning_competitors"
    if stage in {"fetching_reviews", "reviews_complete", "reviews_skipped", "review_fetch_failed"}:
        return "fetching_reviews"
    if stage in {"candidate_scored", "scoring_candidates", "candidate_saved"}:
        return "scoring_candidates"
    if stage in {"dependency_missing", "failed"}:
        return "failed"
    return None


def _human_discovery_error(exc: Exception) -> str:
    raw = str(exc)
    lower = raw.lower()
    if isinstance(exc, ModuleNotFoundError):
        missing = getattr(exc, "name", None) or raw
        if missing == "google_play_scraper":
            return "\u7f3a\u5c11 Google Play \u91c7\u96c6\u4f9d\u8d56\uff0c\u8bf7\u5148\u5b89\u88c5 google-play-scraper\u3002"
        return f"\u7f3a\u5c11\u91c7\u96c6\u4f9d\u8d56\uff1a{missing}\u3002"
    if "proxy" in lower or "connection" in lower or "timeout" in lower or "timed out" in lower:
        return "\u65e0\u6cd5\u7a33\u5b9a\u8bbf\u95ee\u5e94\u7528\u5546\u5e97\uff0c\u8bf7\u68c0\u67e5\u672c\u673a\u4ee3\u7406\u6216\u7f51\u7edc\u8fde\u63a5\u540e\u91cd\u8bd5\u3002"
    if "google_play" in lower or "play store" in lower:
        return "\u5e94\u7528\u5546\u5e97\u91c7\u96c6\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u7f51\u7edc\u3001\u4ee3\u7406\u548c\u91c7\u96c6\u4f9d\u8d56\u3002"
    return raw or "\u673a\u4f1a\u53d1\u73b0\u5931\u8d25\uff0c\u8bf7\u67e5\u770b\u53d1\u73b0\u8fc7\u7a0b\u4e2d\u7684\u5931\u8d25\u6b65\u9aa4\u3002"


def _run_real_play_discovery(store: RunStore, discovery_run_id: str, body: DiscoveryStartBody) -> None:
    latest_counts: dict[str, int] = {
        "searched_query_count": 0,
        "competitor_count": 0,
        "review_group_count": 0,
        "low_score_review_count": 0,
        "candidate_count": 0,
    }

    def sink(stage: str, message: str, payload: dict[str, Any]) -> None:
        status = _discovery_status_for_stage(stage)
        if status and status != "failed":
            store.update_discovery_run(discovery_run_id, status=status)
        if stage == "searching_query":
            latest_counts["searched_query_count"] += 1
        elif stage == "query_search_complete":
            latest_counts["competitor_count"] += int(payload.get("competitor_count") or 0)
        elif stage == "reviews_complete":
            latest_counts["review_group_count"] += 1
            latest_counts["low_score_review_count"] += int(payload.get("low_score_review_count") or 0)
        elif stage == "candidate_scored":
            latest_counts["candidate_count"] += 1
        store.append_discovery_event(discovery_run_id, stage, message, {**payload, "progress": latest_counts.copy()})

    try:
        from hunter.discovery.play_monitor import DEFAULT_SEED_QUERIES, build_play_discovery_run

        queries = body.seed_queries or DEFAULT_SEED_QUERIES
        store.update_discovery_run(discovery_run_id, status="checking_environment")
        store.append_discovery_event(
            discovery_run_id,
            "checking_environment",
            "\u6b63\u5728\u51c6\u5907\u771f\u5b9e\u5e94\u7528\u5546\u5e97\u91c7\u96c6\u3002\u672c\u8f6e\u4e0d\u4f1a\u751f\u6210\u6f14\u793a\u5019\u9009\u3002",
            {"seed_queries": queries, "mode": body.mode},
        )
        result = build_play_discovery_run(
            seed_queries=queries,
            competitors_per_query=body.competitors_per_query,
            reviews_per_app=body.reviews_per_app,
            event_sink=sink,
        )
        searched_apps = result.get("searched_apps") or result.get("competitor_matrix") or []
        if not searched_apps:
            message = "\u5e94\u7528\u5546\u5e97\u641c\u7d22\u6ca1\u6709\u8fd4\u56de\u53ef\u5206\u6790\u7684\u7ade\u54c1\uff0c\u5df2\u505c\u6b62\u3002\u672c\u8f6e\u4e0d\u4f1a\u751f\u6210\u672a\u7ecf\u9a8c\u8bc1\u7684\u5019\u9009\u3002"
            store.update_discovery_run(discovery_run_id, status="failed", error_message=message)
            store.append_discovery_event(discovery_run_id, "failed", message, {"result": result, "progress": latest_counts.copy()})
            return

        reviews = result.get("low_score_reviews") or []
        data_quality = result.get("data_quality") or ("measured" if reviews else "mixed")
        if data_quality == "assumption":
            data_quality = "mixed" if searched_apps else "assumption"
        candidates = result.get("candidate_opportunities") or []
        if not candidates:
            message = "\u5df2\u626b\u63cf\u5230\u7ade\u54c1\uff0c\u4f46\u6ca1\u6709\u5f62\u6210\u53ef\u5165\u6c60\u5019\u9009\u3002\u8bf7\u8c03\u6574\u5173\u952e\u8bcd\u540e\u91cd\u8bd5\u3002"
            store.update_discovery_run(discovery_run_id, status="failed", error_message=message)
            store.append_discovery_event(discovery_run_id, "failed", message, {"result": result, "progress": latest_counts.copy()})
            return

        store.update_discovery_run(discovery_run_id, status="scoring_candidates")
        saved: list[dict[str, Any]] = []
        for raw in candidates:
            if not isinstance(raw, dict):
                continue
            candidate = _candidate_payload(discovery_run_id, raw, data_quality=data_quality)
            if candidate["data_quality"] == "assumption" or not candidate.get("source_apps"):
                store.append_discovery_event(
                    discovery_run_id,
                    "candidate_rejected",
                    "\u4e00\u4e2a\u5019\u9009\u7f3a\u5c11\u771f\u5b9e\u6765\u6e90\u5e94\u7528\uff0c\u5df2\u62d2\u7edd\u5165\u6c60\u3002",
                    {"candidate": candidate},
                )
                continue
            candidate["requirement"] = _requirement_from_candidate(candidate)
            store.upsert_discovery_candidate(candidate)
            saved.append(candidate)
            store.append_discovery_event(
                discovery_run_id,
                "candidate_saved",
                f"\u5019\u9009\u201c{candidate.get('app_name')}\u201d\u5df2\u8fdb\u5165\u9700\u6c42\u6c60\u3002",
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "app_name": candidate.get("app_name"),
                    "evidence_score": candidate.get("evidence_score"),
                    "opportunity_score": candidate.get("opportunity_score"),
                    "build_fit_score": candidate.get("build_fit_score"),
                },
            )
        if not saved:
            message = "\u4e00\u4e2a\u5019\u9009\u7f3a\u5c11\u771f\u5b9e\u6765\u6e90\u5e94\u7528\uff0c\u5df2\u62d2\u7edd\u5165\u6c60\u3002"
            store.update_discovery_run(discovery_run_id, status="failed", error_message=message)
            store.append_discovery_event(discovery_run_id, "failed", message, {"progress": latest_counts.copy()})
            return

        auto_results = []
        if body.mode == "auto":
            for candidate in saved:
                if _passes_auto_discovery_threshold(candidate):
                    auto_results.append(_submit_candidate_to_b(store, candidate["candidate_id"], actor="discovery_auto"))
                    break
        final_status = "auto_submitted" if auto_results else "waiting_for_selection"
        summary = {
            **result,
            "discovery_run_id": discovery_run_id,
            "saved_candidate_count": len(saved),
            "auto_submit_results": auto_results,
            "progress": {
                **latest_counts,
                "competitor_count": len(searched_apps),
                "review_group_count": len(reviews),
                "low_score_review_count": sum(int(r.get("total_low_score_reviews") or 0) for r in reviews if isinstance(r, dict)),
                "candidate_count": len(saved),
            },
        }
        store.update_discovery_run(discovery_run_id, status=final_status, summary=summary)
        store.append_discovery_event(
            discovery_run_id,
            final_status,
            "\u5df2\u6709\u5019\u9009\u81ea\u52a8\u8fdb\u5165\u751f\u6210\u3002" if auto_results else "\u771f\u5b9e\u5019\u9009\u5df2\u8fdb\u5165\u9700\u6c42\u6c60\uff0c\u7b49\u5f85\u4eba\u5de5\u9009\u62e9\u3002",
            {"auto_results": auto_results, "saved_candidate_count": len(saved), "progress": summary["progress"]},
        )
    except Exception as exc:
        logger.exception("real Play discovery failed")
        message = _human_discovery_error(exc)
        store.update_discovery_run(discovery_run_id, status="failed", error_message=message)
        store.append_discovery_event(discovery_run_id, "failed", message, {"error": str(exc), "progress": latest_counts.copy()})

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


# 鈹€鈹€ Rate Limiter (token bucket, per-IP, in-memory) 鈹€鈹€

class _RateLimiter:
    def __init__(self, requests: int = 60, window_seconds: float = 60.0) -> None:
        self._max = requests
        self._window = window_seconds
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def _cleanup(self) -> None:
        now = time.monotonic()
        stale = [k for k, (t, _) in self._buckets.items() if now - t > self._window * 2]
        for k in stale:
            del self._buckets[k]

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._buckets) > 10_000:
                self._cleanup()
            ts, count = self._buckets.get(key, (now, 0))
            if now - ts > self._window:
                ts, count = now, 0
            count += 1
            self._buckets[key] = (ts, count)
            return count <= self._max


_rate_limiter = _RateLimiter(requests=120, window_seconds=60.0)

# Health endpoints exempt from rate limiting
_RATE_EXEMPT = frozenset({"/health", "/readyz"})


def create_app() -> FastAPI:
    app = FastAPI(
        title="Craftsman Agent B",
        version="0.1.0",
        description="澶氬钩鍙拌嚜鍔ㄥ寲杞﹂棿锛圓ndroid 榛樿 / iOS 鍙€夛級鈥?Gate + Build + Release",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Any) -> Any:
        path = request.url.path
        if path not in _RATE_EXEMPT:
            client_ip = request.client.host if request.client else "127.0.0.1"
            if not _rate_limiter.allow(client_ip):
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": "璇锋眰棰戞杩囬珮锛岃绋嶅悗閲嶈瘯",
                            "retryable": True,
                        }
                    },
                )
        return await call_next(request)

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
        archived = _store.archive_legacy_demo_runs()
        if archived:
            _store.append_audit_log(
                event_type="legacy_demo_runs_archived",
                actor="system",
                payload={"count": archived},
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
            handoff = details.get("release_handoff") if isinstance(details.get("release_handoff"), dict) else {}
            handoff_app = handoff.get("app") if isinstance(handoff.get("app"), dict) else {}
            job = release_jobs.get(row["release_id"])
            release_payload.append(
                {
                    "release_id": row["release_id"],
                    "status": row["status"],
                    "updated_at": row["updated_at"],
                    "platform_target": details.get("platform_target"),
                    "app_name": handoff_app.get("name") or handoff.get("app_name"),
                    "package_name": handoff_app.get("bundle_id") or handoff.get("bundle_id") or handoff.get("application_id"),
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

        # Phase 3: Agent D 鈥?embedded earnings summary
        earnings_summary: dict[str, Any] = {
            "configured": bool(settings.play_developer_bucket_id),
            "total_earnings_estimated": 0.0,
            "app_count": 0,
            "status": "not_configured" if not settings.play_developer_bucket_id else "available",
        }
        # 灏濊瘯璇诲彇缂撳瓨鐨勬敹鍏ユ暟鎹紙鑻ユ湁锛?
        try:
            cache_path = _store._db_path.parent / "earnings_cache.json" if hasattr(_store, "_db_path") else None
            if cache_path and cache_path.is_file():
                import json as _json
                cached = _json.loads(cache_path.read_text(encoding="utf-8"))
                earnings_summary.update({
                    "total_earnings_estimated": float(cached.get("total_earnings_estimated", 0.0)),
                    "app_count": int(cached.get("app_count", 0)),
                    "status": "cached",
                })
        except Exception:
            pass

        discovery_candidates = _store.list_discovery_candidates(limit=100)
        opportunities = [_opportunity_from_candidate(candidate) for candidate in discovery_candidates]
        pipeline = _build_pipeline_items(runs, releases, run_jobs, release_jobs)
        agent_status = _build_agent_status(runs, releases, run_jobs, release_jobs)
        discovery_runs = _store.list_discovery_runs(limit=20)
        latest_discovery = discovery_runs[0] if discovery_runs else None
        discovery_events = (
            _store.list_discovery_events(str(latest_discovery.get("discovery_run_id")), limit=300)
            if latest_discovery
            else []
        )
        discovery_progress = _discovery_progress_payload(latest_discovery, discovery_events)

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
                "earnings": earnings_summary,
                "pool": {
                    "configured": bool(settings.package_pool),
                    "used": _store.pool_usage_count()[0],
                    "total": _store.pool_usage_count()[1],
                },
            },
            "opportunities": opportunities,
            "discovery_runs": discovery_runs,
            "latest_discovery": latest_discovery,
            "discovery_events": discovery_events,
            "discovery_progress": discovery_progress,
            "pipeline": pipeline,
            "agent_status": agent_status,
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

    @app.get("/dashboard/api/earnings")
    def dashboard_earnings(
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        """Return cached or live Play earnings summary."""
        if settings.resolved_api_token():
            _require_api_token(x_api_token)
        result: dict[str, Any] = {
            "configured": bool(settings.play_developer_bucket_id),
            "total_gross": 0.0,
            "total_earnings_estimated": 0.0,
            "per_app": {},
            "app_count": 0,
            "status": "not_configured",
            "registered_fee": 25.0,
            "net": -25.0,
            "redeemed": False,
        }
        if not settings.play_developer_bucket_id:
            return result

        result["status"] = "attempting"
        try:
            from hunter.tools.play_earnings import play_get_earnings
            raw = play_get_earnings.invoke({"months": 3})
            import json as _json
            data = _json.loads(raw) if isinstance(raw, str) else raw

            if "sales" in data:
                result["total_gross"] = float(data["sales"].get("total_gross", 0))
            if "earnings" in data:
                result["total_earnings_estimated"] = float(data["earnings"].get("total_earnings_estimated", 0))
            result["per_app"] = (data.get("sales", {}) or {}).get("per_app", {})
            result["app_count"] = int(data.get("sales", {}).get("app_count", 0) or data.get("earnings", {}).get("app_count", 0))
            result["status"] = "fetched"

            # 缂撳瓨鍒版枃浠?
            try:
                assert _store is not None
                db_dir = _store._db_path.parent
                cache_path = db_dir / "earnings_cache.json"
                cache_path.write_text(_json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

            net = result["total_earnings_estimated"] - result["registered_fee"]
            result["net"] = round(net, 2)
            result["redeemed"] = net > 0
        except Exception as exc:
            result["status"] = "error"
            result["error"] = str(exc)

        return result

    def _start_discovery(body: DiscoveryStartBody) -> dict[str, Any]:
        assert _store is not None
        import uuid as _uuid
        from hunter.discovery.play_monitor import DEFAULT_SEED_QUERIES

        mode = body.mode.strip().lower()
        if mode not in {"manual", "auto"}:
            raise HTTPException(
                400,
                detail=_error_detail(code="invalid_discovery_mode", message="mode must be manual or auto"),
            )
        seed_queries = [q.strip() for q in body.seed_queries if q.strip()] or DEFAULT_SEED_QUERIES
        discovery_run_id = "disc-" + _uuid.uuid4().hex[:10]
        normalized = body.model_copy(update={"seed_queries": seed_queries, "mode": mode})
        _store.create_discovery_run(
            discovery_run_id,
            seed_queries=seed_queries,
            categories=body.categories,
            mode=mode,
            operator=body.operator or "dashboard",
        )
        _store.append_discovery_event(
            discovery_run_id,
            "queued",
            "机会发现已开始。系统会查询应用商店数据，并先把候选放入需求池。",
            {"seed_queries": seed_queries, "mode": mode, "categories": body.categories},
        )
        threading.Thread(target=_run_real_play_discovery, args=(_store, discovery_run_id, normalized), daemon=True).start()
        return {
            "started": True,
            "discovery_run_id": discovery_run_id,
            "status": "queued",
            "mode": mode,
            "seed_queries": seed_queries,
            "message": "已开始发现机会。候选会先进入需求池，等待你确认。",
        }

    @app.post("/dashboard/api/discovery-runs")
    def dashboard_start_discovery(
        body: DiscoveryStartBody = Body(default_factory=DiscoveryStartBody),
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        if settings.resolved_api_token():
            _require_api_token(x_api_token)
        return _start_discovery(body)

    @app.post("/dashboard/api/autopilot")
    def dashboard_autopilot(
        body: DiscoveryStartBody = Body(default_factory=DiscoveryStartBody),
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        """Compatibility alias: start real Play discovery only; no fallback/demo run."""
        if settings.resolved_api_token():
            _require_api_token(x_api_token)
        return _start_discovery(body)

    @app.get("/dashboard/api/discovery-runs/{discovery_run_id}")
    def dashboard_discovery_detail(
        discovery_run_id: str,
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        if settings.resolved_api_token():
            _require_api_token(x_api_token)
        assert _store is not None
        run = _store.get_discovery_run(discovery_run_id)
        if not run:
            raise HTTPException(404, detail=_error_detail(code="discovery_run_not_found", message="discovery run not found"))
        return {
            "discovery_run": run,
            "candidates": _store.list_discovery_candidates(discovery_run_id=discovery_run_id, limit=100),
            "events": _store.list_discovery_events(discovery_run_id, limit=500),
        }

    @app.post("/dashboard/api/opportunities/{candidate_id}/implement")
    def dashboard_implement_candidate(
        candidate_id: str,
        body: OpportunityImplementBody = Body(default_factory=OpportunityImplementBody),
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        if settings.resolved_api_token():
            _require_api_token(x_api_token)
        assert _store is not None
        actor = body.operator or "dashboard-operator"
        result = _submit_candidate_to_b(_store, candidate_id, actor=actor)
        return result
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
        quality_blocker = _release_quality_blocker(handoff)
        if quality_blocker:
            _store.upsert_release_state(
                release_id,
                status="needs_manual_action",
                details={
                    **details,
                    "quality_blocker": quality_blocker,
                    "message": quality_blocker["operator_action"],
                },
                updated_by="dashboard",
            )
            return {
                "accepted": False,
                "release_id": release_id,
                "status": "needs_manual_action",
                "quality_blocker": quality_blocker,
            }
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

    # 鈹€鈹€ Package Pool Management 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    @app.post("/dashboard/api/pool/reset")
    def dashboard_pool_reset(
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        """Reset all package allocations so every package becomes available again."""
        if settings.resolved_api_token():
            _require_api_token(x_api_token)
        assert _store is not None
        freed = _store.reset_pool()
        used, total = _store.pool_usage_count()
        return {"ok": True, "freed": freed, "pool": {"used": used, "total": total}}

    @app.post("/dashboard/api/pool/repopulate")
    def dashboard_pool_repopulate(
        x_api_token: str | None = Header(default=None, alias="X-API-Token"),
    ) -> dict[str, Any]:
        """Re-populate pool from .env PACKAGE_POOL setting (adds new ones, keeps existing)."""
        if settings.resolved_api_token():
            _require_api_token(x_api_token)
        assert _store is not None
        pool_setting = (settings.package_pool or "").strip()
        pool_names = [p.strip() for p in pool_setting.split(",") if p.strip()] if pool_setting else []
        added = _store.populate_pool(pool_names) if pool_names else 0
        used, total = _store.pool_usage_count()
        return {"ok": True, "added": added, "pool": {"used": used, "total": total}}

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
        """Run the implementation pipeline synchronously for local debugging."""
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
        quality_blocker = _release_quality_blocker(handoff)
        if quality_blocker:
            _store.upsert_release_state(
                release_id,
                status="needs_manual_action",
                details={
                    **details,
                    "policy": policy,
                    "approval": approval,
                    "quality_blocker": quality_blocker,
                    "platform_target": _release_platform_target(handoff, fallback="android"),
                    "release_handoff": handoff,
                    "message": quality_blocker["operator_action"],
                },
                updated_by="agent_c",
            )
            return _with_contract({
                "release_id": release_id,
                "status": "needs_manual_action",
                "quality_blocker": quality_blocker,
                "message": quality_blocker["operator_action"],
                "policy": policy,
                "approval": approval,
            }, contract_version)
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

"""Derive the unified workflow state from raw Craftsman/Hunter data."""

from __future__ import annotations

from typing import Any, Iterable

CRAFTSMAN_PHASE_ORDER = [
    "spec_normalize",
    "plan",
    "codegen",
    "verify",
    "package",
    "complete",
]

CRAFTSMAN_TERMINAL_OK = {"implementation_complete", "ready_for_release", "submitted"}
CRAFTSMAN_TERMINAL_FAIL = {"failed", "cancelled"}

RELEASE_TERMINAL_OK = {"published", "dry_run_complete"}
RELEASE_TERMINAL_FAIL = {"failed", "prepare_rejected", "platform_unavailable"}


def _step(name: str, label: str) -> dict[str, Any]:
    return {"name": name, "label": label, "status": "pending", "detail": None}


def _last_event(events: Iterable[dict[str, Any]], type_name: str) -> dict[str, Any] | None:
    last = None
    for ev in events:
        if ev.get("type") == type_name:
            last = ev
    return last


def derive_workflow(
    *,
    hunter_events: list[dict[str, Any]],
    craftsman_run: dict[str, Any] | None,
    publisher_release: dict[str, Any] | None,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Return a deterministic workflow representation for the UI.

    Output shape:
        {
            "steps": [ {name, label, status, detail}, ...],
            "active": "discover" | "gate" | ...,
            "headline": short status string,
        }
    """
    steps = [
        _step("discover", "Discover"),
        _step("gate", "Gate"),
        _step("build", "Build"),
        _step("verify", "Verify"),
        _step("publish", "Publish"),
    ]
    by_name = {s["name"]: s for s in steps}

    started = bool(hunter_events) or craftsman_run is not None
    if not started:
        return {"steps": steps, "active": "discover", "headline": "等待启动"}

    blueprint_ev = _last_event(hunter_events, "blueprint")
    if blueprint_ev:
        if blueprint_ev.get("accepted"):
            by_name["discover"]["status"] = "done"
            by_name["discover"]["detail"] = (
                f"{blueprint_ev.get('app_name') or '未命名'} · "
                f"证据 {blueprint_ev.get('evidence_count', 0)} 条"
            )
        else:
            by_name["discover"]["status"] = "failed"
            by_name["discover"]["detail"] = "blueprint rejected"
    else:
        by_name["discover"]["status"] = "running"

    gate_evs = [e for e in hunter_events if e.get("type") == "gate_result"]
    if gate_evs:
        last_gate = gate_evs[-1]
        gate_status = str(last_gate.get("agent_b_status") or "")
        if gate_status == "accepted":
            by_name["gate"]["status"] = "done"
            by_name["gate"]["detail"] = f"rev {last_gate.get('revision')} 通过"
        elif gate_status == "rejected":
            by_name["gate"]["status"] = "failed"
            by_name["gate"]["detail"] = f"rev {last_gate.get('revision')} 拒绝"
        else:
            by_name["gate"]["status"] = "running"
            by_name["gate"]["detail"] = (
                f"rev {last_gate.get('revision')} {gate_status or '澄清中'}"
            )
    elif by_name["discover"]["status"] == "done":
        by_name["gate"]["status"] = "running"

    if craftsman_run is not None:
        run_status = str(craftsman_run.get("status") or "")
        phase = str(craftsman_run.get("phase") or "")
        phase_detail = craftsman_run.get("phase_detail")

        build_phases = {"plan", "codegen"}
        if phase in build_phases:
            by_name["build"]["status"] = "running"
            by_name["build"]["detail"] = phase_detail or phase
        elif phase == "verify":
            by_name["build"]["status"] = "done"
            by_name["verify"]["status"] = "running"
            by_name["verify"]["detail"] = phase_detail or "验证中"
        elif phase in {"package", "complete"}:
            by_name["build"]["status"] = "done"
            by_name["verify"]["status"] = "done"
        elif phase == "failed" or run_status in CRAFTSMAN_TERMINAL_FAIL:
            (
                by_name["verify"]
                if by_name["build"]["status"] == "done"
                else by_name["build"]
            )["status"] = "failed"

        if run_status in CRAFTSMAN_TERMINAL_OK:
            by_name["build"]["status"] = "done"
            by_name["verify"]["status"] = "done"
        elif run_status and by_name["build"]["status"] == "pending":
            by_name["build"]["status"] = "running"

    pub_started = _last_event(hunter_events, "publish_start") is not None
    if publisher_release is not None or pub_started:
        rel_status = ""
        agent_c = ""
        if publisher_release:
            rel_status = str(publisher_release.get("status") or "").lower()
            agent_c = str(publisher_release.get("agent_c_status") or "").lower()
        if rel_status in RELEASE_TERMINAL_OK or agent_c in {"dry_run_complete", "published"}:
            by_name["publish"]["status"] = "done"
            by_name["publish"]["detail"] = rel_status or agent_c
        elif rel_status in RELEASE_TERMINAL_FAIL or agent_c == "failed":
            by_name["publish"]["status"] = "failed"
            by_name["publish"]["detail"] = rel_status or agent_c
        else:
            by_name["publish"]["status"] = "running"
            by_name["publish"]["detail"] = rel_status or agent_c or "提交中"

    meta_status = str(meta.get("status") or "")
    if meta_status == "complete":
        if by_name["verify"]["status"] == "pending":
            by_name["verify"]["status"] = "done"
    if meta_status in {"failed", "stopped"}:
        for s in steps:
            if s["status"] == "running":
                s["status"] = "failed"
                break

    active = next((s["name"] for s in steps if s["status"] == "running"), None)
    if active is None:
        last_done = None
        for s in steps:
            if s["status"] in {"done", "failed"}:
                last_done = s["name"]
        active = last_done or "discover"

    headline = _headline(steps, meta_status)
    return {"steps": steps, "active": active, "headline": headline}


def _headline(steps: list[dict[str, Any]], meta_status: str) -> str:
    failed = next((s for s in steps if s["status"] == "failed"), None)
    if failed:
        return f"{failed['label']} 失败：{failed['detail'] or '-'}"
    running = next((s for s in steps if s["status"] == "running"), None)
    if running:
        return f"{running['label']} 进行中：{running['detail'] or '-'}"
    if all(s["status"] == "done" for s in steps if s["name"] != "publish"):
        if steps[-1]["status"] == "done":
            return "全部完成"
        if steps[-1]["status"] == "pending":
            return "实现完成 · 未启用发布"
    if meta_status == "stopped":
        return "已停止"
    return "等待启动"

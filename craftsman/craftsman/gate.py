from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from craftsman.config import settings
from craftsman.llm import analyze_requirement_llm
from craftsman.requirement_normalize import normalize_requirement, soft_fill_requirement


@dataclass
class GateResult:
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    suggested_rules: list[str] = field(default_factory=list)
    summary: str = ""
    estimated_complexity: str = "low"
    open_questions: list[str] = field(default_factory=list)


def _is_soft_mode() -> bool:
    return settings.gate_mode.strip().lower() == "soft"


def _estimate_complexity(req: dict[str, Any]) -> str:
    features = req.get("features") or []
    score = len(features)
    persistence = (req.get("core_logic") or {}).get("persistence")
    if persistence == "SwiftData":
        score += 2
    elif persistence in ("UserDefaults", "SharedPreferences"):
        score += 1
    if score <= 3:
        return "low"
    if score <= 6:
        return "medium"
    return "high"


def _estimate_hours(req: dict[str, Any]) -> float:
    complexity = _estimate_complexity(req)
    features = req.get("features") or []
    item_count = sum(len(f.get("items") or []) for f in features)
    base = {"low": 0.8, "medium": 1.4, "high": 2.2}[complexity]
    detail = min(item_count * 0.04, 0.6)
    return round(base + detail, 1)


def _check_evidence_and_quality(
    req: dict[str, Any],
    reasons: list[str],
    rules: list[str],
    *,
    soft: bool,
) -> None:
    dq = req.get("data_quality")
    evidence = req.get("evidence") or []

    if not dq:
        msg = "未标注 data_quality（measured | assumption | mixed）"
        if soft:
            rules.append(msg)
        else:
            reasons.append(msg)
        return

    if not evidence:
        msg = "缺少 evidence 条目（至少 1 条 query/source/snippet）"
        if soft:
            rules.append(msg)
        else:
            reasons.append(msg)
        return

    assumption_sources = sum(
        1 for item in evidence if str(item.get("source", "")).startswith("assumption://")
    )
    real_sources = len(evidence) - assumption_sources

    if dq == "measured" and assumption_sources > 0 and real_sources == 0:
        msg = "data_quality=measured 但 evidence 全部为 assumption 来源"
        if soft:
            rules.append(msg)
        else:
            reasons.append(msg)

    if dq == "assumption" and real_sources > 0 and assumption_sources == 0:
        msg = "data_quality=assumption 但 evidence 未标注 assumption://"
        if soft:
            rules.append(msg)
        else:
            reasons.append(msg)

    for idx, item in enumerate(evidence, start=1):
        if not str(item.get("query", "")).strip():
            msg = f"evidence[{idx}] 缺少 query"
            (rules if soft else reasons).append(msg)
        if not str(item.get("snippet", "")).strip():
            msg = f"evidence[{idx}] 缺少 snippet"
            (rules if soft else reasons).append(msg)


def _fatal_missing(req: dict[str, Any]) -> list[str]:
    fatal: list[str] = []
    app = req.get("app") or {}
    if not str(app.get("name") or "").strip():
        fatal.append("app.name 缺失")
    if not str(app.get("bundle_id") or "").strip():
        fatal.append("app.bundle_id 缺失")
    features = req.get("features") or []
    if not features:
        fatal.append("features 为空")
    return fatal


def run_gate(req: dict[str, Any], schema_errors: list[str]) -> GateResult:
    soft = _is_soft_mode()
    req = normalize_requirement(req)
    if soft:
        req = soft_fill_requirement(req)

    reasons: list[str] = []
    rules: list[str] = []
    open_q: list[str] = []

    fatal = _fatal_missing(req)
    reasons.extend(fatal)

    if schema_errors:
        for err in schema_errors[:5]:
            if soft:
                rules.append(f"schema: {err}")
            else:
                reasons.append(f"schema: {err}")
        if soft:
            rules.append("需求必须符合 requirement.v1.json schema")

    app = req.get("app") or {}
    app_name = app.get("name", "Unknown")

    core = req.get("core_logic") or {}
    if not core.get("persistence"):
        msg = "core_logic 未说明存储方式"
        if soft:
            rules.append(msg)
        else:
            reasons.append(msg)
            rules.append("core_logic.persistence 必填: none | UserDefaults | SwiftData | SharedPreferences")

    ui = req.get("ui_layout") or {}
    if not ui.get("navigation"):
        msg = "ui_layout 未定义导航结构"
        if soft:
            rules.append(msg)
        else:
            reasons.append(msg)
            rules.append("ui_layout.navigation 必填: stack | tab | single")

    store = req.get("store") or {}
    if not store.get("privacy_url"):
        msg = "store 缺少 privacy_url"
        if soft:
            rules.append(msg)
        else:
            reasons.append(msg)
            rules.append("store.privacy_url 必填（App Store 审核）")

    branding = req.get("branding") or {}
    if not branding.get("primary_color"):
        msg = "branding 缺少 primary_color"
        if soft:
            rules.append(msg)
        else:
            reasons.append(msg)
            rules.append("branding.primary_color 必填，格式 #RRGGBB")

    budget = req.get("budget") or {}
    max_features = int(budget.get("max_features", settings.max_features))
    max_hours = float(budget.get("max_hours", 2.0))
    features = req.get("features") or []

    if len(features) > max_features:
        if soft:
            rules.append(f"功能数量 {len(features)} 超过上限 {max_features}（已截断）")
        else:
            reasons.append(f"功能数量 {len(features)} 超过上限 {max_features}")
            rules.append(f"单 opportunity 功能数 ≤ {max_features}")

    est_hours = _estimate_hours(req)
    complexity = _estimate_complexity(req)
    if est_hours > max_hours:
        overrun = est_hours - max_hours
        if soft or overrun <= 1.0:
            open_q.append(
                f"预估开发 {est_hours:.1f}h 略高于预算 {max_hours}h，实现时将优先 MVP 裁剪。"
            )
            rules.append("若需严格控时，可缩小 features.items 或提高 budget.max_hours")
        else:
            reasons.append(f"预估开发 {est_hours:.1f}h 超过预算 {max_hours}h")
            rules.append("缩小 scope 或提高 budget.max_hours")

    _check_evidence_and_quality(req, reasons, rules, soft=soft)

    applied = set(req.get("applied_rules") or [])
    for rule in rules:
        if rule not in applied and "必填" in rule and not soft:
            open_q.append(f"请落实规则: {rule}")

    llm_extra = analyze_requirement_llm(req)
    if llm_extra:
        rules.extend(llm_extra.get("suggested_rules") or [])
        open_q.extend(llm_extra.get("open_questions") or [])

    summary_parts = [f"{app_name}：{len(features)} 个功能屏"]
    if core.get("persistence"):
        summary_parts.append(f"持久化 {core['persistence']}")
    summary = "，".join(summary_parts)

    if soft and settings.gate_auto_accept and not fatal:
        accepted = True
        reasons = []
    else:
        accepted = len(reasons) == 0

    return GateResult(
        accepted=accepted,
        reasons=reasons,
        suggested_rules=list(dict.fromkeys(rules)),
        summary=summary,
        estimated_complexity=complexity,
        open_questions=list(dict.fromkeys(open_q)),
    )

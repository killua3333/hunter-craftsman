from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from craftsman.config import settings
from craftsman.llm import analyze_requirement_llm
from craftsman.requirement_normalize import normalize_requirement


@dataclass
class GateResult:
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    suggested_rules: list[str] = field(default_factory=list)
    summary: str = ""
    estimated_complexity: str = "low"
    open_questions: list[str] = field(default_factory=list)


def _estimate_complexity(req: dict[str, Any]) -> str:
    """按功能屏数量估算；capabilities 为实现说明，不计入功能屏。"""
    features = req.get("features") or []
    score = len(features)
    persistence = (req.get("core_logic") or {}).get("persistence")
    if persistence == "SwiftData":
        score += 2
    elif persistence == "UserDefaults":
        score += 1
    if score <= 3:
        return "low"
    if score <= 6:
        return "medium"
    return "high"


def _estimate_hours(req: dict[str, Any]) -> float:
    """
    粗算纯前端 MVP 工时（小时）。
    与 capabilities 条数解耦，避免把权限/通知说明误当成额外功能屏。
    """
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
) -> None:
    """校验 Agent A 标注的 data_quality 与 evidence。"""
    dq = req.get("data_quality")
    evidence = req.get("evidence") or []

    if not dq:
        reasons.append("未标注 data_quality（measured | assumption | mixed）")
        rules.append("必须标注 data_quality，并与 evidence 来源一致")
        return

    if not evidence:
        reasons.append("缺少 evidence 条目（至少 1 条 query/source/snippet）")
        rules.append(
            "web_search 后写入 evidence；纯假设时 source 用 assumption:// 并说明依据"
        )
        return

    assumption_sources = sum(
        1 for item in evidence if str(item.get("source", "")).startswith("assumption://")
    )
    real_sources = len(evidence) - assumption_sources

    if dq == "measured" and assumption_sources > 0 and real_sources == 0:
        reasons.append("data_quality=measured 但 evidence 全部为 assumption 来源")
        rules.append("measured 时 evidence 应含 web_search 返回的真实 URL")

    if dq == "assumption" and real_sources > 0 and assumption_sources == 0:
        reasons.append("data_quality=assumption 但 evidence 未标注 assumption://")
        rules.append("assumption 时至少一条 evidence.source 使用 assumption://")

    for idx, item in enumerate(evidence, start=1):
        if not str(item.get("query", "")).strip():
            reasons.append(f"evidence[{idx}] 缺少 query")
        if not str(item.get("snippet", "")).strip():
            reasons.append(f"evidence[{idx}] 缺少 snippet")


def run_gate(req: dict[str, Any], schema_errors: list[str]) -> GateResult:
    req = normalize_requirement(req)
    reasons: list[str] = []
    rules: list[str] = []
    open_q: list[str] = []

    if schema_errors:
        reasons.extend([f"schema: {e}" for e in schema_errors[:5]])
        rules.append("需求必须符合 requirement.v1.json schema")

    app = req.get("app") or {}
    app_name = app.get("name", "Unknown")

    core = req.get("core_logic") or {}
    if not core.get("persistence"):
        reasons.append("core_logic 未说明存储方式")
        rules.append("core_logic.persistence 必填: none | UserDefaults | SwiftData")

    ui = req.get("ui_layout") or {}
    if not ui.get("navigation"):
        reasons.append("ui_layout 未定义导航结构")
        rules.append("ui_layout.navigation 必填: stack | tab | single")

    store = req.get("store") or {}
    if not store.get("privacy_url"):
        reasons.append("store 缺少 privacy_url")
        rules.append("store.privacy_url 必填（App Store 审核）")

    branding = req.get("branding") or {}
    if not branding.get("primary_color"):
        reasons.append("branding 缺少 primary_color")
        rules.append("branding.primary_color 必填，格式 #RRGGBB")

    budget = req.get("budget") or {}
    max_features = int(budget.get("max_features", settings.max_features))
    max_hours = float(budget.get("max_hours", 2.0))
    features = req.get("features") or []

    if len(features) > max_features:
        reasons.append(f"功能数量 {len(features)} 超过上限 {max_features}")
        rules.append(f"单 opportunity 功能数 ≤ {max_features}")

    est_hours = _estimate_hours(req)
    complexity = _estimate_complexity(req)
    if est_hours > max_hours:
        overrun = est_hours - max_hours
        # 略超预算：不硬拒，记入开放问题，仍允许 implement（由 codegen 按 MVP 裁剪）
        if overrun <= 1.0:
            open_q.append(
                f"预估开发 {est_hours:.1f}h 略高于预算 {max_hours}h，"
                "实现时将优先核心计时与统计，可精简设置项。"
            )
            rules.append("若需严格控时，可缩小 features.items 或提高 budget.max_hours")
        else:
            reasons.append(f"预估开发 {est_hours:.1f}h 超过预算 {max_hours}h")
            rules.append("缩小 scope 或提高 budget.max_hours")

    _check_evidence_and_quality(req, reasons, rules)

    applied = set(req.get("applied_rules") or [])
    for rule in rules:
        if rule not in applied and "必填" in rule:
            open_q.append(f"请落实规则: {rule}")

    llm_extra = analyze_requirement_llm(req)
    if llm_extra:
        # chat 模型仅补充建议与开放问题，不阻塞 Gate（避免误报「缺字段」等）
        rules.extend(llm_extra.get("suggested_rules") or [])
        open_q.extend(llm_extra.get("open_questions") or [])

    summary_parts = [f"{app_name}：{len(features)} 个功能屏"]
    if core.get("persistence"):
        summary_parts.append(f"持久化 {core['persistence']}")
    summary = "，".join(summary_parts)

    accepted = len(reasons) == 0
    return GateResult(
        accepted=accepted,
        reasons=reasons,
        suggested_rules=list(dict.fromkeys(rules)),
        summary=summary,
        estimated_complexity=complexity,
        open_questions=list(dict.fromkeys(open_q)),
    )

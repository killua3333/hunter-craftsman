"""A→B 编排：analyze → 澄清修订 → implement（最多 3 轮）。"""

from __future__ import annotations

import json
from typing import Any

from hunter.agents.specialist import SpecialistSession
from hunter.feedback import save_feedback_raw
from hunter.orchestrator.repair import ensure_blueprint
from hunter.integrations.craftsman import (
    build_requirement_from_blueprint,
    run_analyze,
    run_sync_implementation,
)
from hunter.schemas import AppOpportunityBlueprint

MAX_CLARIFICATION_ROUNDS = 3
_TERMINAL_STATUSES = frozenset(
    {
        "implementation_failed",
        "ready_for_release",
        "submitted",
        "platform_unavailable",
        "rejected",
    }
)


def _build_clarification_prompt(feedback: dict[str, Any], revision: int) -> str:
    reasons = feedback.get("reasons") or []
    rules = feedback.get("suggested_rules") or []
    questions = (feedback.get("blueprint") or {}).get("open_questions") or []
    return (
        f"Agent B 返回 needs_clarification（第 {revision} 轮修订）。"
        "请根据以下反馈修订机会单，输出**完整** AppOpportunityBlueprint JSON（含 requirement、evidence、data_quality）。\n\n"
        f"## reasons\n{json.dumps(reasons, ensure_ascii=False, indent=2)}\n\n"
        f"## suggested_rules\n{json.dumps(rules, ensure_ascii=False, indent=2)}\n\n"
        f"## open_questions\n{json.dumps(questions, ensure_ascii=False, indent=2)}\n"
    )


def run_blueprint_pipeline(
    blueprint: AppOpportunityBlueprint,
    *,
    session: SpecialistSession | None = None,
    base_url: str = "http://127.0.0.1:8791",
    opportunity_id: str | None = None,
    timeout_seconds: float = 600.0,
    max_rounds: int = MAX_CLARIFICATION_ROUNDS,
    save_feedback: bool = True,
) -> dict[str, Any]:
    """
    从已有机会单启动：Gate analyze → 必要时用 session 澄清 → implement。

    chat 的 /make 与 run 的后半段共用此函数。
    """
    if not blueprint.accepted:
        return {
            "accepted": False,
            "blueprint": blueprint.model_dump(),
            "feedback": None,
        }

    clarify_session = session or SpecialistSession()
    oid = opportunity_id
    revision = 1
    analyze_history: list[dict[str, Any]] = []

    for round_num in range(1, max_rounds + 1):
        requirement = build_requirement_from_blueprint(
            blueprint,
            opportunity_id=oid,
            revision=revision,
        )
        oid = requirement["opportunity_id"]

        feedback = run_analyze(requirement, base_url=base_url, timeout_seconds=60.0)
        analyze_history.append({"revision": revision, "feedback": feedback})
        status = feedback.get("agent_b_status", "")

        if status == "needs_clarification":
            if round_num >= max_rounds:
                if save_feedback:
                    save_feedback_raw(feedback)
                return {
                    "accepted": True,
                    "blueprint": blueprint.model_dump(),
                    "requirement": requirement,
                    "revision": revision,
                    "rounds": round_num,
                    "analyze_history": analyze_history,
                    "feedback": feedback,
                    "stopped": "max_clarification_rounds",
                }
            revision += 1
            clarify = clarify_session.send(_build_clarification_prompt(feedback, revision))
            blueprint = clarify.get("blueprint")
            if blueprint is None or not blueprint.accepted:
                return {
                    "accepted": False,
                    "blueprint": blueprint.model_dump() if blueprint else None,
                    "revision": revision,
                    "rounds": round_num,
                    "analyze_history": analyze_history,
                    "feedback": feedback,
                    "stopped": "clarification_failed",
                }
            continue

        if status == "accepted":
            impl_feedback = run_sync_implementation(
                requirement,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
            )
            if save_feedback:
                save_feedback_raw(impl_feedback)
            return {
                "accepted": True,
                "blueprint": blueprint.model_dump(),
                "requirement": requirement,
                "revision": revision,
                "rounds": round_num,
                "analyze_history": analyze_history,
                "feedback": impl_feedback,
            }

        if status in _TERMINAL_STATUSES:
            if save_feedback:
                save_feedback_raw(feedback)
            return {
                "accepted": status != "rejected",
                "blueprint": blueprint.model_dump(),
                "requirement": requirement,
                "revision": revision,
                "rounds": round_num,
                "analyze_history": analyze_history,
                "feedback": feedback,
                "stopped": f"gate_status_{status}",
            }

        raise RuntimeError(f"unexpected agent_b_status from Gate: {status}")

    raise RuntimeError("unreachable")


def run_opportunity_pipeline(
    question: str,
    *,
    base_url: str = "http://127.0.0.1:8791",
    opportunity_id: str | None = None,
    timeout_seconds: float = 600.0,
    max_rounds: int = MAX_CLARIFICATION_ROUNDS,
    save_feedback: bool = True,
) -> dict[str, Any]:
    """
    完整编排：Agent A 出单 → Gate analyze → 必要时澄清 → implement。

    返回 dict：blueprint, requirement, revision, rounds, analyze_history, feedback
    """
    session = SpecialistSession()
    blueprint, result = ensure_blueprint(session, question, max_attempts=3)
    if not blueprint.accepted:
        return {
            "accepted": False,
            "blueprint": blueprint.model_dump(),
            "answer": result.get("answer"),
            "feedback": None,
        }

    outcome = run_blueprint_pipeline(
        blueprint,
        session=session,
        base_url=base_url,
        opportunity_id=opportunity_id,
        timeout_seconds=timeout_seconds,
        max_rounds=max_rounds,
        save_feedback=save_feedback,
    )
    return outcome

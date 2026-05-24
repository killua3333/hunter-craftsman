"""A→B 编排：analyze → 澄清修订 → implement（最多 3 轮）。"""

from __future__ import annotations

import json
from typing import Any, Callable

from hunter.agents.specialist import SpecialistSession
from hunter.feedback import save_feedback_raw
from hunter.orchestrator.repair import ensure_blueprint
from hunter.integrations.craftsman import (
    build_requirement_from_blueprint,
    craftsman_analyze_timeout_seconds,
    run_analyze,
    run_sync_implementation,
    start_implementation,
    wait_for_run_completion,
)
from hunter.integrations.publisher import run_publish_pipeline
from hunter.schemas import AppOpportunityBlueprint

MAX_CLARIFICATION_ROUNDS = 3
MAX_AUTOPILOT_OPPORTUNITY_ATTEMPTS = 3
_TERMINAL_STATUSES = frozenset(
    {
        "implementation_failed",
        "implementation_complete",
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


def _attach_correlation(outcome: dict[str, Any]) -> dict[str, Any]:
    cid = outcome.get("run_id") or outcome.get("correlation_id")
    if cid:
        outcome["correlation_id"] = str(cid)
    feedback = outcome.get("feedback") or {}
    if feedback.get("run_id"):
        outcome["correlation_id"] = str(feedback["run_id"])
    return outcome


def _maybe_publish(
    outcome: dict[str, Any],
    *,
    base_url: str,
    publish: bool,
    auto_approve_release: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not publish:
        return outcome
    feedback = outcome.get("feedback") or {}
    if feedback.get("agent_b_status") != "implementation_complete":
        outcome["publish"] = {"publish_status": "skipped", "reason": "implementation not complete"}
        return outcome
    handoff = feedback.get("release_handoff")
    platform = (handoff or {}).get("platform") if isinstance(handoff, dict) else {}
    target = str((platform or {}).get("target") or "android").lower()
    if target != "android":
        outcome["publish"] = {"publish_status": "skipped", "reason": f"platform {target} uses non-android publisher"}
        return outcome
    try:
        outcome["publish"] = run_publish_pipeline(
            feedback,
            base_url=base_url,
            auto_approve=auto_approve_release,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=2.0,
        )
    except (RuntimeError, ValueError) as exc:
        outcome["publish"] = {"publish_status": "failed", "error": str(exc)}
    return outcome


AUTOPILOT_TRIGGER = (
    "Autopilot 已启动。请自动搜索 Google Play 工具类 app 机会，"
    "选定 1 个最适合纯前端 Android MVP 的方向，"
    "输出 accepted=true 的完整 AppOpportunityBlueprint JSON（含 requirement）。"
)


def run_autopilot_pipeline(
    *,
    base_url: str = "http://127.0.0.1:8791",
    opportunity_id: str | None = None,
    timeout_seconds: float = 600.0,
    poll_interval_seconds: float = 2.0,
    use_async_implement: bool = True,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    max_rounds: int = MAX_CLARIFICATION_ROUNDS,
    save_feedback: bool = True,
    publish: bool = False,
    auto_approve_release: bool = True,
    max_opportunity_attempts: int = MAX_AUTOPILOT_OPPORTUNITY_ATTEMPTS,
) -> dict[str, Any]:
    """人类仅触发「开始」：自动发现机会 → B → 可选 C；失败可 pick 下一个机会。"""
    from hunter.agents.specialist import DiscoverySession
    from hunter.feedback.inline_learnings import append_inline_learning

    attempts: list[dict[str, Any]] = []
    last_outcome: dict[str, Any] | None = None

    for attempt in range(1, max_opportunity_attempts + 1):
        session = DiscoverySession()
        trigger = AUTOPILOT_TRIGGER
        if attempt > 1:
            trigger += f"\n\n（第 {attempt} 次选品：请避开上一轮失败方向，换一个新的工具类机会。）"
        blueprint, result = ensure_blueprint(session, trigger, max_attempts=3)
        if blueprint is None:
            last_outcome = {
                "accepted": False,
                "blueprint": None,
                "answer": result.get("answer"),
                "feedback": None,
                "mode": "autopilot",
                "stopped": "discovery_parse_failed",
                "autopilot_attempt": attempt,
            }
            attempts.append(last_outcome)
            continue
        if not blueprint.accepted:
            blueprint = blueprint.model_copy(update={"accepted": True})

        outcome = run_blueprint_pipeline(
            blueprint,
            session=session,
            base_url=base_url,
            opportunity_id=opportunity_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            use_async_implement=use_async_implement,
            progress_callback=progress_callback,
            max_rounds=max_rounds,
            save_feedback=save_feedback,
            publish=publish,
            auto_approve_release=auto_approve_release,
        )
        outcome["mode"] = "autopilot"
        outcome["discovery_answer"] = result.get("answer")
        outcome["autopilot_attempt"] = attempt
        attempts.append(outcome)
        last_outcome = outcome

        feedback = outcome.get("feedback") or {}
        status = str(feedback.get("agent_b_status") or "")
        if status == "implementation_complete":
            outcome["autopilot_attempts"] = attempts
            return _attach_correlation(outcome)

        oid = str(feedback.get("opportunity_id") or opportunity_id or "unknown")
        append_inline_learning(
            opportunity_id=oid,
            reason=f"autopilot attempt {attempt} failed: {status}",
            feedback=feedback if isinstance(feedback, dict) else None,
        )
        if attempt >= max_opportunity_attempts:
            break

    if last_outcome is None:
        last_outcome = {
            "accepted": False,
            "mode": "autopilot",
            "stopped": "autopilot_exhausted",
            "autopilot_attempts": attempts,
        }
    else:
        last_outcome["autopilot_attempts"] = attempts
        last_outcome.setdefault("stopped", "autopilot_exhausted")
    return _attach_correlation(last_outcome)


def run_blueprint_pipeline(
    blueprint: AppOpportunityBlueprint,
    *,
    session: SpecialistSession | None = None,
    base_url: str = "http://127.0.0.1:8791",
    opportunity_id: str | None = None,
    timeout_seconds: float = 600.0,
    poll_interval_seconds: float = 2.0,
    use_async_implement: bool = True,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    max_rounds: int = MAX_CLARIFICATION_ROUNDS,
    save_feedback: bool = True,
    publish: bool = False,
    auto_approve_release: bool = True,
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

        feedback = run_analyze(
            requirement,
            base_url=base_url,
            timeout_seconds=craftsman_analyze_timeout_seconds(),
        )
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
            if blueprint is None:
                return {
                    "accepted": False,
                    "blueprint": None,
                    "revision": revision,
                    "rounds": round_num,
                    "analyze_history": analyze_history,
                    "feedback": feedback,
                    "stopped": "clarification_failed",
                }
            if not blueprint.accepted:
                blueprint = blueprint.model_copy(update={"accepted": True})
            continue

        if status == "accepted":
            if use_async_implement:
                run = start_implementation(
                    requirement,
                    base_url=base_url,
                    timeout_seconds=60.0,
                )
                run_id = run.get("run_id")
                if not run_id:
                    raise RuntimeError(f"craftsman implement missing run_id: {run}")
                impl_feedback = wait_for_run_completion(
                    str(run_id),
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    on_event=progress_callback,
                )
                impl_feedback.setdefault("run_id", run_id)
            else:
                impl_feedback = run_sync_implementation(
                    requirement,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                )
            if save_feedback:
                save_feedback_raw(impl_feedback)
            outcome = {
                "accepted": True,
                "blueprint": blueprint.model_dump(),
                "requirement": requirement,
                "revision": revision,
                "rounds": round_num,
                "analyze_history": analyze_history,
                "run_id": impl_feedback.get("run_id"),
                "feedback": impl_feedback,
            }
            return _attach_correlation(
                _maybe_publish(
                outcome,
                base_url=base_url,
                publish=publish,
                auto_approve_release=auto_approve_release,
                timeout_seconds=timeout_seconds,
            )
            )

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
    poll_interval_seconds: float = 2.0,
    use_async_implement: bool = True,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    max_rounds: int = MAX_CLARIFICATION_ROUNDS,
    save_feedback: bool = True,
    publish: bool = False,
    auto_approve_release: bool = True,
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
        poll_interval_seconds=poll_interval_seconds,
        use_async_implement=use_async_implement,
        progress_callback=progress_callback,
        max_rounds=max_rounds,
        save_feedback=save_feedback,
        publish=publish,
        auto_approve_release=auto_approve_release,
    )
    return _attach_correlation(outcome)

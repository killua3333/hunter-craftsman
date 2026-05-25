from __future__ import annotations

from datetime import datetime, timezone

from craftsman.models import AgentBStatus, Blueprint, CraftsmanFeedback


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def build_feedback(
    *,
    opportunity_id: str,
    revision: int,
    app_name: str,
    accepted: bool,
    status: AgentBStatus,
    reasons: list[str] | None = None,
    suggested_rules: list[str] | None = None,
    summary: str | None = None,
    estimated_complexity: str | None = None,
    open_questions: list[str] | None = None,
    run_id: str | None = None,
    artifacts: dict | None = None,
    release_handoff: dict | None = None,
    verification: str | None = None,
) -> CraftsmanFeedback:
    return CraftsmanFeedback(
        opportunity_id=opportunity_id,
        revision=revision,
        blueprint=Blueprint(
            app_name=app_name,
            accepted=accepted,
            summary=summary,
            estimated_complexity=estimated_complexity,
            open_questions=open_questions or [],
        ),
        agent_b_status=status,
        reasons=reasons or [],
        suggested_rules=suggested_rules or [],
        created_at=utc_now(),
        run_id=run_id,
        artifacts=artifacts,
        release_handoff=release_handoff,
        verification=verification,
    )

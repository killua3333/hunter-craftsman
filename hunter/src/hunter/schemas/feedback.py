"""Agent B → Hunter feedback contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class AgentBFeedback(BaseModel):
    schema_version: str = "1.0"
    opportunity_id: str = Field(description="Opportunity identifier")
    revision: int = Field(ge=1, description="Requirement revision")
    agent_b_status: str = Field(
        description=(
            "needs_clarification | rejected | accepted | in_progress | "
            "implementation_failed | implementation_complete | ready_for_release | "
            "submitted | platform_unavailable"
        )
    )
    reasons: list[str] = Field(default_factory=list, description="Failure or guidance reasons")
    suggested_rules: list[str] = Field(default_factory=list, description="Guidance for next revision")
    blueprint: dict[str, Any] | None = Field(
        default=None,
        description="Optional Agent A blueprint summary",
    )
    run_id: str | None = Field(default=None, description="Run identifier from Agent B")
    artifacts: dict[str, Any] | None = Field(default=None, description="Artifact metadata")
    release_handoff: dict[str, Any] | None = Field(
        default=None,
        description="Reserved handoff contract for future release agent",
    )
    notes: str | None = Field(default=None, description="Additional note")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO8601 timestamp",
    )

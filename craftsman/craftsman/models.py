from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentBStatus(StrEnum):
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    IMPLEMENTATION_FAILED = "implementation_failed"
    IMPLEMENTATION_COMPLETE = "implementation_complete"
    NEEDS_POLISH = "needs_polish"
    READY_FOR_RELEASE = "ready_for_release"
    SUBMITTED = "submitted"
    PLATFORM_UNAVAILABLE = "platform_unavailable"


class Blueprint(BaseModel):
    app_name: str
    accepted: bool
    summary: str | None = None
    estimated_complexity: str | None = None
    open_questions: list[str] = Field(default_factory=list)


class CraftsmanFeedback(BaseModel):
    schema_version: str = "1.0"
    opportunity_id: str
    revision: int
    blueprint: Blueprint
    agent_b_status: AgentBStatus
    reasons: list[str] = Field(default_factory=list)
    suggested_rules: list[str] = Field(default_factory=list)
    created_at: datetime
    run_id: str | None = None
    artifacts: dict[str, Any] | None = None
    release_handoff: dict[str, Any] | None = None
    verification: str | None = None
    quality_report: dict[str, Any] | None = None
    quality_score: int | None = None
    release_ready: bool | None = None
    polish_required: bool | None = None
    quality_failure_classes: list[str] = Field(default_factory=list)

    def to_agent_a_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", exclude_none=True)
        data["created_at"] = self.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        bp = data.get("blueprint", {})
        if not bp.get("open_questions"):
            bp.pop("open_questions", None)
        return data


class EvidenceItem(BaseModel):
    query: str
    source: str
    snippet: str


class RequirementPayload(BaseModel):
    schema_version: str
    opportunity_id: str
    revision: int
    platform: dict[str, Any] | None = None
    app: dict[str, Any]
    features: list[dict[str, Any]]
    data_quality: str | None = None
    evidence: list[EvidenceItem] | list[dict[str, Any]] | None = None
    core_logic: dict[str, Any] | None = None
    ui_layout: dict[str, Any] | None = None
    branding: dict[str, Any] | None = None
    capabilities: list[str] | None = None
    store: dict[str, Any] | None = None
    applied_rules: list[str] | None = None
    budget: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class RunRecord(BaseModel):
    run_id: str
    opportunity_id: str
    revision: int
    status: str
    requirement_json: str
    feedback_json: str | None = None
    workspace_path: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ReleaseHandoff(BaseModel):
    """Reserved handoff contract for future release agent."""

    schema_version: str = "1.0"
    run_id: str
    opportunity_id: str
    revision: int
    platform: dict[str, Any] | None = None
    requirement_digest: str
    release_bundle: dict[str, Any]
    build_provenance: dict[str, Any]
    agent_b_status: str = AgentBStatus.IMPLEMENTATION_COMPLETE.value

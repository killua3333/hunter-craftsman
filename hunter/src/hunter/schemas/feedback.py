"""Agent B → Hunter 反馈契约。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class AgentBFeedback(BaseModel):
    opportunity_id: str = Field(description="与机会单对应的唯一 ID")
    agent_b_status: str = Field(
        description="implementation_ok | implementation_failed | rejected_scope 等"
    )
    reasons: list[str] = Field(min_length=1, description="失败或改进原因")
    blueprint: dict[str, Any] | None = Field(
        default=None,
        description="可选：Agent A 输出的机会单快照",
    )
    suggested_rules: list[str] = Field(
        default_factory=list,
        description="建议 Agent A 下次遵循的规则",
    )
    notes: str | None = Field(default=None, description="补充说明")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO8601 时间戳",
    )

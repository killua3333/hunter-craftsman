"""
Agent A → Agent B 的输出契约。

DeepSeek 等模型不支持 OpenAI `response_format` 解析时，从助手文本中提取 JSON 并校验。
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from hunter.schemas.normalize import normalize_blueprint_dict


class EvidenceItem(BaseModel):
    """市场调研证据（来自 web_search 或明确标注的假设）。"""

    query: str = Field(description="检索 query 或假设主题")
    source: str = Field(description="来源 URL；纯假设时写 assumption://...")
    snippet: str = Field(description="摘录或假设说明")


class BlueprintApp(BaseModel):
    name: str
    bundle_id: str = Field(pattern=r"^[a-zA-Z0-9.-]+$")
    application_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9._]+$")
    version: str = "1.0.0"
    build: str = "1"
    min_ios: str | None = "17.0"
    min_android_sdk: str | None = "24"

    @model_validator(mode="after")
    def _fill_platform_app_defaults(self) -> BlueprintApp:
        if not (self.application_id or "").strip():
            self.application_id = self.bundle_id
        return self


class BlueprintPlatform(BaseModel):
    target: Literal["android", "ios"] = "android"


class BlueprintFeature(BaseModel):
    id: str
    type: Literal["list", "form", "detail", "tab_root"]
    title: str
    items: list[str] = Field(default_factory=list)


class BlueprintCoreLogic(BaseModel):
    persistence: Literal["none", "UserDefaults", "SwiftData", "SharedPreferences"]
    description: str


class BlueprintUiLayout(BaseModel):
    navigation: Literal["stack", "tab", "single"]
    screens: list[str] = Field(default_factory=list)


class BlueprintBranding(BaseModel):
    primary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    accent_color: str | None = None
    icon_text: str = Field(max_length=2)


class BlueprintStore(BaseModel):
    subtitle: str
    description: str
    keywords: list[str] = Field(default_factory=list)
    privacy_url: str


class BlueprintBudget(BaseModel):
    max_features: int = 8
    max_hours: float = 2.0


class BlueprintRequirement(BaseModel):
    """与 Craftsman requirement.v1 对齐的详细需求（accepted=true 时必填）。"""

    platform: BlueprintPlatform = Field(default_factory=BlueprintPlatform)
    app: BlueprintApp
    features: list[BlueprintFeature] = Field(min_length=1)
    core_logic: BlueprintCoreLogic
    ui_layout: BlueprintUiLayout
    branding: BlueprintBranding
    store: BlueprintStore
    budget: BlueprintBudget = Field(default_factory=BlueprintBudget)
    capabilities: list[str] = Field(default_factory=list)
    applied_rules: list[str] = Field(default_factory=list)


class AppOpportunityBlueprint(BaseModel):
    """
    Hunter（Agent A）结构化输出。

    - accepted=false：仅填写 rejection_reason
    - accepted=true：填写摘要字段 + requirement + evidence/data_quality
    """

    accepted: bool = Field(
        description="是否通过极简 ROI 护栏。true 时本对象可作为 Agent B 的输入。"
    )
    rejection_reason: str | None = Field(
        default=None,
        description="accepted=false 时必填：否决原因",
    )
    app_name: str = Field(default="", description="应用名称（应与 requirement.app.name 一致）")
    core_logic: str = Field(
        default="",
        description="核心逻辑一句话摘要（应与 requirement.core_logic.description 一致）",
    )
    ui_layout: str = Field(
        default="",
        description="UI 布局一句话摘要",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="上架关键词（应与 store.keywords 一致）",
    )
    data_quality: Literal["measured", "assumption", "mixed"] | None = Field(
        default=None,
        description="市场结论依据：实测 / 假设 / 混合",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="web_search 证据；纯假设时 source 用 assumption://",
    )
    requirement: BlueprintRequirement | None = Field(
        default=None,
        description="完整 requirement.v1 结构，供 Agent B 直接实现",
    )

    @field_validator("keywords")
    @classmethod
    def _normalize_keywords(cls, v: list[str]) -> list[str]:
        return [k.strip() for k in v if k and k.strip()]

    @model_validator(mode="after")
    def _validate_guardrail_output(self) -> AppOpportunityBlueprint:
        if self.accepted:
            missing = []
            if not self.app_name.strip():
                missing.append("app_name")
            if not self.core_logic.strip():
                missing.append("core_logic")
            if not self.ui_layout.strip():
                missing.append("ui_layout")
            if len(self.keywords) < 1:
                missing.append("keywords")
            if self.data_quality is None:
                missing.append("data_quality")
            if self.requirement is None:
                missing.append("requirement")
            if missing:
                raise ValueError(
                    f"accepted=true 时以下字段不能为空: {', '.join(missing)}"
                )
            if self.data_quality == "measured" and not self.evidence:
                raise ValueError(
                    "data_quality=measured 时 evidence 至少 1 条（含 query/source/snippet）"
                )
            if self.data_quality in ("assumption", "mixed") and not self.evidence:
                raise ValueError(
                    "data_quality=assumption|mixed 时 evidence 至少 1 条，"
                    "source 使用 assumption:// 并说明依据"
                )
            req = self.requirement
            assert req is not None
            if req.app.name.strip() != self.app_name.strip():
                raise ValueError("requirement.app.name 必须与 app_name 一致")
        elif not (self.rejection_reason or "").strip():
            raise ValueError("accepted=false 时必须提供 rejection_reason")
        return self


def format_parse_error(exc: BaseException) -> str:
    """将校验异常格式化为用户可读说明。"""
    if isinstance(exc, ValidationError):
        lines: list[str] = []
        for err in exc.errors()[:10]:
            loc = ".".join(str(part) for part in err.get("loc", ()))
            lines.append(f"  - {loc}: {err.get('msg')}")
        return "JSON 校验失败:\n" + "\n".join(lines)
    return str(exc)


def parse_blueprint(data: dict[str, Any] | str | AppOpportunityBlueprint) -> AppOpportunityBlueprint:
    """解析、规范化并校验 Agent A 输出。"""
    if isinstance(data, AppOpportunityBlueprint):
        return data
    if isinstance(data, str):
        payload: Any = json.loads(data)
    else:
        payload = data
    if not isinstance(payload, dict):
        raise ValueError("AppOpportunityBlueprint 必须是 JSON 对象")
    normalized = normalize_blueprint_dict(payload)
    return AppOpportunityBlueprint.model_validate(normalized)


def load_blueprint_dict_from_text(text: str) -> dict[str, Any]:
    """从助手文本中提取 JSON 对象（未校验）。"""
    raw = text.strip()
    if not raw:
        raise ValueError("回复为空，无法解析 AppOpportunityBlueprint")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        payload = json.loads(fence.group(1).strip())
        if isinstance(payload, dict):
            return payload
        raise ValueError("JSON 根节点必须是对象")

    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    if start < 0:
        raise ValueError("回复中未找到有效的 AppOpportunityBlueprint JSON")

    depth = 0
    for i in range(start, len(raw)):
        ch = raw[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = raw[start : i + 1]
                try:
                    payload = json.loads(chunk)
                except json.JSONDecodeError:
                    from json import JSONDecoder

                    payload, _ = JSONDecoder().raw_decode(chunk)
                if isinstance(payload, dict):
                    return payload
                raise ValueError("JSON 根节点必须是对象")

    raise ValueError("回复中未找到完整的 JSON 对象")


def blueprint_for_agent_b(blueprint: AppOpportunityBlueprint) -> dict[str, Any]:
    """提取传给 Agent B 的 payload；未通过护栏时抛出 ValueError。"""
    if not blueprint.accepted:
        raise ValueError(blueprint.rejection_reason or "机会未通过护栏")
    if blueprint.requirement is None:
        raise ValueError("accepted=true 但缺少 requirement")
    # Agent B 契约不接受 null，外发 payload 统一去除 None 字段。
    return blueprint.requirement.model_dump(exclude_none=True)


def format_blueprint_json(blueprint: AppOpportunityBlueprint) -> str:
    """美化打印用。"""
    return json.dumps(blueprint.model_dump(exclude_none=True), ensure_ascii=False, indent=2)


def extract_blueprint_from_text(text: str) -> AppOpportunityBlueprint:
    """从模型回复中提取 JSON（支持 ```json 代码块或裸 JSON），并规范化后校验。"""
    return parse_blueprint(load_blueprint_dict_from_text(text))


def extract_blueprint_from_messages(
    messages: list[Any],
) -> tuple[AppOpportunityBlueprint | None, str | None]:
    """
    从消息列表中取最后一条可解析的助手 JSON。

    返回 (blueprint, error_message)；成功时 error 为 None。
    """
    from langchain_core.messages import AIMessage

    last_error: str | None = None
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if not content:
            continue
        if msg.tool_calls and not str(content).strip():
            continue
        text = content if isinstance(content, str) else str(content)
        try:
            return extract_blueprint_from_text(text), None
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            last_error = format_parse_error(exc)
            continue
    return None, last_error



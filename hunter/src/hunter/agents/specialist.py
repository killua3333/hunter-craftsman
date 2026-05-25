"""
专精 Agent：System 角色 + Tools + ReAct 循环（LangGraph）。

每轮请求会将 system prompt 与 messages 一并送入模型；
模型若产生 tool_calls，运行时执行工具并写入 ToolMessage，再继续推理。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from hunter.config import get_agent_settings, get_chat_model
from hunter.prompts import load_discovery_prompt, load_system_prompt
from hunter.schemas import (
    AppOpportunityBlueprint,
    extract_blueprint_from_messages,
    format_blueprint_json,
    format_parse_error,
    parse_blueprint,
)
from hunter.tools import get_default_tools, get_discovery_tools

_DISCOVERY_JSON_RULE = """
## 最终输出（Autopilot 必遵）
最后一条助手消息必须是**纯 JSON**。必须 `accepted: true` 并含完整 requirement。
features 每项含 id、title、type、items（字符串数组）；platform.target 默认 android。
"""

_JSON_OUTPUT_RULE = """
## 最终输出格式（必遵）
完成调研与护栏判断后，你的**最后一条助手消息**必须是**仅包含一个 JSON 对象**的纯文本（不要用 Markdown 标题或其它说明包裹）。

accepted=true 时必填：app_name, core_logic, ui_layout, keywords, data_quality, evidence, requirement

### requirement.features（必遵形状，否则 /make 不可用）
每项必须是：{"id": "timer", "type": "list|form|detail|tab_root", "title": "显示名", "items": ["字符串1", "字符串2"]}
禁止：用 name 代替 id/title；items 里放对象；缺少 id 或 title。

### requirement.store.keywords
必须是字符串数组：["番茄钟", "专注"]，禁止逗号拼成的单个字符串。

### requirement.platform
必须输出：{"target": "android"|"ios"}；用户未指定平台时默认 target="android"。

### 篇幅控制（防截断）
- requirement.features 建议 2～4 项；每项 items 最多 5 条短句
- core_logic.description、ui_layout.screens 各 1～2 句摘要即可，细节放进 items

### 最小示例（结构须一致，内容可替换）
{"accepted": true, "app_name": "极简番茄钟", "core_logic": "本地番茄计时", "ui_layout": "单屏倒计时+按钮", "keywords": ["番茄钟", "专注"], "data_quality": "measured", "evidence": [{"query": "番茄钟 差评", "source": "https://example.com", "snippet": "广告太多"}], "requirement": {"app": {"name": "极简番茄钟", "bundle_id": "com.hunter.pomodoro"}, "features": [{"id": "timer", "type": "list", "title": "计时", "items": ["25分钟倒计时", "开始暂停"]}], "core_logic": {"persistence": "SharedPreferences", "description": "Android 用 SharedPreferences / iOS 用 UserDefaults 存今日次数"}, "ui_layout": {"navigation": "single", "screens": ["主屏倒计时"]}, "branding": {"primary_color": "#E74C3C", "icon_text": "番"}, "store": {"subtitle": "极简专注", "description": "离线番茄钟", "keywords": ["番茄钟", "专注"], "privacy_url": "https://example.com/privacy"}, "budget": {"max_features": 8, "max_hours": 2}}}

accepted=false 时：{"accepted": false, "rejection_reason": "原因", "app_name": "", "core_logic": "", "ui_layout": "", "keywords": [], "evidence": []}
"""


def build_discovery_agent():
    """Autopilot：Play 搜索 + 发现 prompt。"""
    model = get_chat_model()
    system_prompt = load_discovery_prompt() + _DISCOVERY_JSON_RULE
    return create_react_agent(
        model,
        get_discovery_tools(),
        prompt=system_prompt,
        checkpointer=MemorySaver(),
    )


def build_specialist_agent(*, extra_tools: list | None = None):
    """构建带系统提示词与工具的 ReAct Agent 图（JSON 由文本解析，兼容 DeepSeek）。"""
    model = get_chat_model()
    tools = get_default_tools()
    if extra_tools:
        tools = [*tools, *extra_tools]

    system_prompt = load_system_prompt() + _JSON_OUTPUT_RULE
    return create_react_agent(
        model,
        tools,
        prompt=system_prompt,
        checkpointer=MemorySaver(),
    )


def _last_ai_content(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return ""


class DiscoverySession:
    """Autopilot 发现会话：自动搜索 Play 机会并出单。"""

    def __init__(self, *, thread_id: str | None = None) -> None:
        self.agent = build_discovery_agent()
        self.thread_id = thread_id or f"autopilot-{uuid4().hex[:8]}"
        agent_cfg = get_agent_settings()
        max_iterations = int(agent_cfg.get("max_iterations", 12))
        self._config = {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": max_iterations,
        }

    def send(self, user_input: str) -> dict[str, Any]:
        result = self.agent.invoke(
            {"messages": [("user", user_input)]},
            config=self._config,
        )
        messages = result.get("messages", [])
        blueprint, parse_error = extract_blueprint_from_messages(messages)
        if blueprint is not None and not blueprint.accepted:
            blueprint = blueprint.model_copy(update={"accepted": True})
        return {
            "answer": _format_user_answer(blueprint, _last_ai_content(messages)),
            "blueprint": blueprint,
            "blueprint_json": (
                format_blueprint_json(blueprint) if blueprint is not None else None
            ),
            "parse_error": parse_error,
            "messages": messages,
            "raw": result,
            "mode": "autopilot",
        }


class SpecialistSession:
    """可跨多轮保留上下文的专精 agent 会话。"""

    def __init__(self, *, thread_id: str | None = None) -> None:
        self.agent = build_specialist_agent()
        self.thread_id = thread_id or f"session-{uuid4().hex[:8]}"
        agent_cfg = get_agent_settings()
        max_iterations = int(agent_cfg.get("max_iterations", 10))
        self._config = {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": max_iterations,
        }

    def send(self, user_input: str) -> dict[str, Any]:
        """发送一条用户消息，返回本轮回答与完整消息轨迹。"""
        result = self.agent.invoke(
            {"messages": [("user", user_input)]},
            config=self._config,
        )
        messages = result.get("messages", [])
        blueprint, parse_error = extract_blueprint_from_messages(messages)
        if blueprint is None and result.get("structured_response") is not None:
            try:
                blueprint = parse_blueprint(result["structured_response"])
                parse_error = None
            except Exception as exc:
                parse_error = format_parse_error(exc)
        return {
            "answer": _format_user_answer(blueprint, _last_ai_content(messages)),
            "blueprint": blueprint,
            "blueprint_json": (
                format_blueprint_json(blueprint) if blueprint is not None else None
            ),
            "parse_error": parse_error,
            "messages": messages,
            "raw": result,
        }


def _format_user_answer(
    blueprint: AppOpportunityBlueprint | None,
    fallback: str,
) -> str:
    if blueprint is not None:
        return format_blueprint_json(blueprint)
    return fallback


def run_specialist(
    user_input: str,
    *,
    thread_id: str = "default",
) -> dict[str, Any]:
    """单轮调用（无会话记忆）。多轮请使用 SpecialistSession。"""
    session = SpecialistSession(thread_id=thread_id)
    return session.send(user_input)

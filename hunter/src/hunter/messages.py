"""
Message 类型说明与辅助构造（对应 LangChain / Chat API 角色）：

- SystemMessage: 开发者设定的全局规则与角色（system）
- HumanMessage:    用户输入（user）
- AIMessage:       模型回复，可含 tool_calls（assistant）
- ToolMessage:     工具执行结果，需对应 tool_call_id（tool）
"""

from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


def build_conversation(
    system_text: str,
    user_text: str,
) -> list[BaseMessage]:
    """构造一轮对话的起始消息列表。"""
    return [
        SystemMessage(content=system_text),
        HumanMessage(content=user_text),
    ]


def append_tool_result(
    messages: list[BaseMessage],
    *,
    tool_call_id: str,
    content: str,
    tool_name: str | None = None,
) -> list[BaseMessage]:
    """在已有消息列表后追加 ToolMessage（工具执行结果）。"""
    return [
        *messages,
        ToolMessage(
            content=content,
            tool_call_id=tool_call_id,
            name=tool_name,
        ),
    ]


__all__ = [
    "AIMessage",
    "HumanMessage",
    "SystemMessage",
    "ToolMessage",
    "build_conversation",
    "append_tool_result",
]

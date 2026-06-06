"""Agent A JSON 解析失败时的自动修正。"""

from __future__ import annotations

from hunter.agents.specialist import SpecialistSession
from hunter.schemas import AppOpportunityBlueprint

_STEP_LIMIT_MARKERS = ("need more steps", "more steps to process")

REPAIR_PROMPT = (
    "你上一条助手消息中的 JSON 未通过程序校验，无法进入 Autopilot 流水线。\n"
    "错误如下：\n{error}\n\n"
    "请**仅**输出修正后的完整 AppOpportunityBlueprint JSON（纯 JSON，无 Markdown）。\n"
    "必遵：\n"
    "- 顶层含 app_name, core_logic, ui_layout, keywords, data_quality, evidence, requirement\n"
    "- 禁止 app_idea / opportunity 外层；evidence 为 [{{query,source,snippet}}]\n"
    "- features 最多 3 项；每项 id、title、type=list|form|detail|tab_root；items 为字符串数组（每项≤3条）\n"
    "- requirement 含 app, core_logic.description, ui_layout, branding, store\n"
    "- ui_layout.navigation 只能是 stack|tab|single（多 Tab 用 tab，禁止 tab_root）\n"
    "- 总 JSON 尽量控制在 3500 字符以内，避免被截断"
)

REPAIR_STEP_LIMIT_PROMPT = (
    "上一轮因 ReAct 步数上限中断，未输出 JSON。\n"
    "请**不要调用任何工具**，根据对话里已有的 play_search 结果（若无则用 assumption），\n"
    "**仅**输出完整 AppOpportunityBlueprint JSON（纯 JSON，无 Markdown）。\n"
    "features 最多 3 项、每项 items 最多 3 条；禁止 app_idea/opportunity 外层。"
)


def _hit_step_limit(answer: str | None) -> bool:
    text = (answer or "").lower()
    return any(marker in text for marker in _STEP_LIMIT_MARKERS)


def _repair_message(parse_error: str, answer: str | None) -> str:
    if _hit_step_limit(answer):
        return REPAIR_STEP_LIMIT_PROMPT
    return REPAIR_PROMPT.format(error=parse_error)


def ensure_blueprint(
    session: SpecialistSession,
    user_input: str,
    *,
    max_attempts: int = 3,
) -> tuple[AppOpportunityBlueprint, dict]:
    """
    发送用户问题并解析 blueprint；失败时用同 session 自动修正，最多 max_attempts 次。
    """
    result = session.send(user_input)
    blueprint: AppOpportunityBlueprint | None = result.get("blueprint")

    for _ in range(max_attempts - 1):
        if blueprint is not None:
            return blueprint, result
        parse_error = result.get("parse_error") or "无法从助手消息中提取 JSON 对象"
        if _hit_step_limit(result.get("answer")):
            parse_error = (
                "LangGraph 步数用尽（模型回复 need more steps）；"
                "请减少工具调用或提高 discovery_max_iterations"
            )
        result = session.send(_repair_message(parse_error, result.get("answer")))
        blueprint = result.get("blueprint")

    if blueprint is None:
        err = result.get("parse_error") or "未知解析错误"
        preview = (result.get("answer") or "")[:1500]
        hints = (
            "LangGraph 步数用尽（回复含 need more steps）— 已尝试无工具修复；"
            "可增大 config/settings.yaml 的 discovery_max_iterations，"
            "或确认 autopilot 只调 1 次 play_search"
            if _hit_step_limit(preview)
            else "JSON 被 Markdown 包裹、features 缺 id/title、或 requirement 过长被截断"
        )
        raise ValueError(
            "Agent A 未输出可解析 JSON\n"
            f"解析说明: {err}\n"
            f"（可用 hunter chat -v 查看完整助手回复；常见原因：{hints}）\n"
            f"回复摘要:\n{preview}"
        )
    return blueprint, result

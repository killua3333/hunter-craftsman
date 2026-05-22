"""Agent A JSON 解析失败时的自动修正。"""

from __future__ import annotations

from hunter.agents.specialist import SpecialistSession
from hunter.schemas import AppOpportunityBlueprint

REPAIR_PROMPT = (
    "你上一条助手消息中的 JSON 未通过程序校验，无法进入 /make 或 run 流水线。\n"
    "错误如下：\n{error}\n\n"
    "请**仅**输出修正后的完整 AppOpportunityBlueprint JSON（纯 JSON，无 Markdown）。\n"
    "必遵：features 每项含 id、title、type；items 只能是字符串数组；"
    "store.keywords 为字符串数组；requirement 不要过长，每个 feature 的 items 最多 5 条。"
)


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
        result = session.send(REPAIR_PROMPT.format(error=parse_error))
        blueprint = result.get("blueprint")

    if blueprint is None:
        err = result.get("parse_error") or "未知解析错误"
        preview = (result.get("answer") or "")[:1500]
        raise ValueError(
            "Agent A 未输出可解析 JSON\n"
            f"解析说明: {err}\n"
            f"（可用 hunter chat -v 查看完整助手回复；常见原因：JSON 被 Markdown 包裹、"
            f"features 缺 id/title、或 requirement 过长被截断）\n"
            f"回复摘要:\n{preview}"
        )
    return blueprint, result

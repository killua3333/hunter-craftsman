from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml
from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from hunter.paths import CONFIG_DIR

load_dotenv()

# 思考/推理模型在 LangGraph 多步调用时需回传 reasoning_content，当前链路不支持
_UNSUPPORTED_AGENT_MODELS = frozenset({
    "deepseek-reasoner",
    "deepseek-r1",
    "deepseek-v4-pro",
})


def validate_model_for_agent(model_name: str) -> None:
    """agent 带工具与多轮时，需使用普通对话模型。"""
    normalized = model_name.strip().lower()
    if normalized in _UNSUPPORTED_AGENT_MODELS or "reasoner" in normalized:
        raise ValueError(
            f"模型「{model_name}」属于思考/推理模型，与 hunter 的工具调用、多轮记忆不兼容，"
            f"请在 config/settings.yaml 或环境变量 HUNTER_MODEL_NAME 中改为 deepseek-chat。"
        )


@lru_cache
def load_settings() -> dict[str, Any]:
    path = CONFIG_DIR / "settings.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_chat_model() -> BaseChatModel:
    """根据 config/settings.yaml 与环境变量创建聊天模型。"""
    settings = load_settings()
    model_cfg = settings.get("model", {})

    provider = model_cfg.get("provider", "deepseek")
    model_name = os.getenv("HUNTER_MODEL_NAME") or model_cfg.get("name", "deepseek-chat")
    validate_model_for_agent(model_name)
    temperature = float(model_cfg.get("temperature", 0.2))

    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = (
            os.getenv("DEEPSEEK_API_BASE")
            or os.getenv("OPENAI_API_BASE")
            or model_cfg.get("base_url", "https://api.deepseek.com/v1")
        )
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE") or model_cfg.get("base_url")
    else:
        raise ValueError(f"暂不支持的 model.provider: {provider}（可选: openai, deepseek）")

    kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": temperature,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    return ChatOpenAI(**kwargs)


def get_agent_settings() -> dict[str, Any]:
    return load_settings().get("agent", {})

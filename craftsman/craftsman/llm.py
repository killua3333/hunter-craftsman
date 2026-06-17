from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any

from craftsman.config import ROOT, settings
from craftsman.prompts import load_prompt

logger = logging.getLogger(__name__)

_HIG_PATH = ROOT / "context" / "hig-swiftui-lite.md"
_CODEGEN_SYSTEM = "craftsman_codegen_system"
_ANDROID_CODEGEN_SYSTEM = "craftsman_android_codegen_system"
_GATE_SYSTEM = "craftsman_gate_system"
_USAGE_EVENTS: ContextVar[list[dict[str, Any]] | None] = ContextVar("craftsman_llm_usage_events", default=None)


def _client():
    api_key = settings.resolved_api_key()
    if not api_key:
        return None
    from openai import OpenAI

    return OpenAI(
        api_key=api_key,
        base_url=settings.resolved_api_base(),
        timeout=float(settings.llm_request_timeout_seconds),
    )


def _unit_prices_per_1k(model: str) -> tuple[float, float]:
    if model == settings.deepseek_chat_model:
        return settings.llm_price_chat_input_per_1k, settings.llm_price_chat_output_per_1k
    if model == settings.deepseek_pro_model:
        return settings.llm_price_pro_input_per_1k, settings.llm_price_pro_output_per_1k
    return 0.0, 0.0


def reset_usage_events() -> None:
    _USAGE_EVENTS.set([])


def usage_summary() -> dict[str, Any]:
    events = _USAGE_EVENTS.get() or []
    by_model: dict[str, dict[str, Any]] = {}
    total_prompt = 0
    total_completion = 0
    total_cost = 0.0
    for event in events:
        model = str(event.get("model") or "unknown")
        bucket = by_model.setdefault(
            model,
            {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
            },
        )
        prompt_tokens = int(event.get("prompt_tokens") or 0)
        completion_tokens = int(event.get("completion_tokens") or 0)
        total_tokens = int(event.get("total_tokens") or 0)
        cost = float(event.get("estimated_cost_usd") or 0.0)
        bucket["calls"] += 1
        bucket["prompt_tokens"] += prompt_tokens
        bucket["completion_tokens"] += completion_tokens
        bucket["total_tokens"] += total_tokens
        bucket["estimated_cost_usd"] += cost
        total_prompt += prompt_tokens
        total_completion += completion_tokens
        total_cost += cost
    return {
        "calls": len(events),
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "estimated_cost_usd": round(total_cost, 6),
        "by_model": by_model,
    }


def _chat_json(
    *,
    model: str,
    system: str,
    user: str,
    temperature: float,
) -> dict[str, Any] | None:
    client = _client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        usage = getattr(resp, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)
        input_per_1k, output_per_1k = _unit_prices_per_1k(model)
        estimated_cost_usd = (
            (prompt_tokens / 1000.0) * input_per_1k
            + (completion_tokens / 1000.0) * output_per_1k
        )
        events = _USAGE_EVENTS.get()
        if events is not None:
            events.append(
                {
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "estimated_cost_usd": round(estimated_cost_usd, 6),
                }
            )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as exc:
        logger.warning("LLM call failed model=%s: %s", model, exc)
        return None


def _files_from_response(data: dict[str, Any] | None) -> dict[str, str] | None:
    if not data:
        return None
    out: dict[str, str] = {}
    for item in data.get("files") or []:
        path = item.get("path")
        content = item.get("content")
        if path and content is not None:
            out[str(path)] = str(content)
    return out or None


def _build_context_text(req: dict[str, Any]) -> str:
    ctx = req.get("agent_a_context") or {}
    if not isinstance(ctx, dict):
        return ""
    parts: list[str] = []
    summary = str(ctx.get("summary") or "").strip()
    if summary:
        parts.append(f"Agent A summary:\n{summary}")
    complexity = str(ctx.get("estimated_complexity") or "").strip()
    if complexity:
        parts.append(f"Agent A complexity: {complexity}")
    open_questions = ctx.get("open_questions") or []
    if open_questions:
        parts.append(
            "Agent A open questions:\n"
            + json.dumps(open_questions, ensure_ascii=False, indent=2)
        )
    reasons = ctx.get("reasons") or []
    if reasons:
        parts.append(
            "Agent A reasons:\n"
            + json.dumps(reasons, ensure_ascii=False, indent=2)
        )
    return "\n\n".join(parts)


def _build_codegen_prompt(req: dict[str, Any]) -> str:
    context = _build_context_text(req)
    hints = (
        "Implementation checklist:\n"
        "- Implement every declared feature with concrete interaction behavior.\n"
        "- Keep persistence behavior aligned with core_logic.persistence.\n"
        "- Mirror ui_layout.screens in the UI structure instead of collapsing to a generic screen.\n"
        "- Use branding.primary_color as the primary accent.\n"
        "- Do not add undeclared features or backend/network logic.\n"
        "- Return complete file contents only.\n"
    )
    requirement_json = json.dumps(req, ensure_ascii=False, indent=2)
    if context:
        return f"{context}\n\n{hints}\nRequirement JSON:\n{requirement_json}"
    return f"{hints}\nRequirement JSON:\n{requirement_json}"


def analyze_requirement_llm(req: dict[str, Any]) -> dict[str, Any] | None:
    """Gate 语义补充（反馈 Agent A）— 使用 deepseek-chat。"""
    hig = _HIG_PATH.read_text(encoding="utf-8") if _HIG_PATH.exists() else ""
    system = load_prompt(_GATE_SYSTEM)
    context = _build_context_text(req)
    user = f"HIG 摘要:\n{hig[:4000]}\n\n"
    if context:
        user += f"{context}\n\n"
    user += f"需求 JSON:\n{json.dumps(req, ensure_ascii=False)}"
    data = _chat_json(
        model=settings.deepseek_chat_model,
        system=system,
        user=user,
        temperature=0.2,
    )
    if not data:
        return None
    return {
        "reasons": list(data.get("reasons") or []),
        "suggested_rules": list(data.get("suggested_rules") or []),
        "open_questions": list(data.get("open_questions") or []),
    }


def generate_code_llm(req: dict[str, Any], *, platform: str = "ios") -> dict[str, str] | None:
    """根据 requirement 生成源码 — 使用 deepseek-v4-pro。"""
    target = platform.strip().lower()
    if target == "android":
        system = load_prompt(_ANDROID_CODEGEN_SYSTEM)
        required = {"app/src/main/java/com/craftsman/MainActivity.kt"}
    else:
        system = load_prompt(_CODEGEN_SYSTEM)
        required = {"Sources/App.swift", "Sources/ContentView.swift", "Sources/Color+Hex.swift"}
    user = _build_codegen_prompt(req)
    data = _chat_json(
        model=settings.deepseek_pro_model,
        system=system,
        user=user,
        temperature=0.1,
    )
    files = _files_from_response(data)
    if not files:
        return None
    if not required.issubset(files.keys()):
        logger.warning(
            "codegen missing required %s files, got: %s",
            target,
            sorted(files.keys()),
        )
        return None
    return files


def fix_code_llm(
    req: dict[str, Any],
    files: dict[str, str],
    errors: list[dict[str, Any]],
    round_num: int,
    *,
    platform: str = "ios",
) -> dict[str, str] | None:
    """Reflexion 修错 — 使用 deepseek-v4-pro。"""
    if platform.strip().lower() == "android":
        system = (
            "你是 Android Kotlin/Compose 编译错误修复专家。"
            '只返回 JSON: {"files":[{"path":"相对路径","content":"全文"}]}。'
            "只修改出错的 Kotlin 文件，保持 package com.craftsman 不变；不要输出 Swift 语法。"
        )
    else:
        system = (
            "你是 Swift/SwiftUI 编译错误修复专家。"
            '只返回 JSON: {"files":[{"path":"相对路径","content":"全文"}]}。'
            "仅修改必要文件，保持与需求一致。"
        )
    user = (
        f"轮次: {round_num}\n"
        f"应用: {req.get('app', {}).get('name')}\n"
        f"{_build_context_text(req)}\n"
        f"编译错误:\n{json.dumps(errors, ensure_ascii=False)}\n"
        f"当前文件:\n{json.dumps(files, ensure_ascii=False)[:12000]}"
    )
    data = _chat_json(
        model=settings.deepseek_pro_model,
        system=system,
        user=user,
        temperature=0.1,
    )
    return _files_from_response(data)

from __future__ import annotations

import json
import logging
from typing import Any

from craftsman.config import ROOT, settings
from craftsman.prompts import load_prompt

logger = logging.getLogger(__name__)

_HIG_PATH = ROOT / "context" / "hig-swiftui-lite.md"
_CODEGEN_SYSTEM = "craftsman_codegen_system"
_GATE_SYSTEM = "craftsman_gate_system"


def _client():
    api_key = settings.resolved_api_key()
    if not api_key:
        return None
    from openai import OpenAI

    return OpenAI(api_key=api_key, base_url=settings.resolved_api_base())


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


def analyze_requirement_llm(req: dict[str, Any]) -> dict[str, Any] | None:
    """Gate 语义补充（反馈 Agent A）— 使用 deepseek-chat。"""
    hig = _HIG_PATH.read_text(encoding="utf-8") if _HIG_PATH.exists() else ""
    system = load_prompt(_GATE_SYSTEM)
    user = (
        f"HIG 摘要:\n{hig[:4000]}\n\n"
        f"需求 JSON:\n{json.dumps(req, ensure_ascii=False)}"
    )
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


def generate_code_llm(req: dict[str, Any]) -> dict[str, str] | None:
    """根据 requirement 生成 Swift 源码 — 使用 deepseek-v4-pro。"""
    system = load_prompt(_CODEGEN_SYSTEM)
    user = json.dumps(req, ensure_ascii=False, indent=2)
    data = _chat_json(
        model=settings.deepseek_pro_model,
        system=system,
        user=user,
        temperature=0.1,
    )
    files = _files_from_response(data)
    if not files:
        return None
    required_swift = {"Sources/App.swift", "Sources/ContentView.swift", "Sources/Color+Hex.swift"}
    if not required_swift.issubset(files.keys()):
        logger.warning(
            "codegen missing required Swift files, got: %s",
            sorted(files.keys()),
        )
        return None
    return files


def fix_code_llm(
    req: dict[str, Any],
    files: dict[str, str],
    errors: list[dict[str, Any]],
    round_num: int,
) -> dict[str, str] | None:
    """Reflexion 修错 — 使用 deepseek-v4-pro。"""
    system = (
        "你是 Swift/SwiftUI 编译错误修复专家。"
        "只返回 JSON: {\"files\":[{\"path\":\"相对路径\",\"content\":\"全文\"}]}。"
        "仅修改必要文件，保持与需求一致。"
    )
    user = (
        f"轮次: {round_num}\n"
        f"应用: {req.get('app', {}).get('name')}\n"
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

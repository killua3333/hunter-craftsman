"""失败即时 learnings — 写入 prompt 上下文（非仅周报）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from hunter.paths import PROMPTS_DIR

INLINE_LEARNINGS_PATH = PROMPTS_DIR / "inline_learnings.md"
_MAX_ENTRIES = 20


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_inline_learning(
    *,
    opportunity_id: str,
    reason: str,
    feedback: dict | None = None,
) -> None:
    """追加一条失败摘要，供 Discovery/Spec 会话读取。"""
    entry = {
        "at": _utc_now(),
        "opportunity_id": opportunity_id,
        "reason": reason[:500],
        "agent_b_status": (feedback or {}).get("agent_b_status"),
        "reasons": ((feedback or {}).get("reasons") or [])[:5],
    }
    INLINE_LEARNINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if INLINE_LEARNINGS_PATH.is_file():
        lines = INLINE_LEARNINGS_PATH.read_text(encoding="utf-8").splitlines()
    lines.append(f"- [{entry['at']}] {entry['opportunity_id']}: {entry['reason']}")
    if entry.get("reasons"):
        lines.append(f"  - details: {json.dumps(entry['reasons'], ensure_ascii=False)}")
    trimmed = lines[-(_MAX_ENTRIES * 2) :]
    header = "# Inline learnings (auto, from recent failures)\n"
    INLINE_LEARNINGS_PATH.write_text(header + "\n".join(trimmed) + "\n", encoding="utf-8")


def load_inline_learnings() -> str:
    if not INLINE_LEARNINGS_PATH.is_file():
        return ""
    return INLINE_LEARNINGS_PATH.read_text(encoding="utf-8").strip()

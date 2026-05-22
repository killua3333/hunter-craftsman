"""从 Craftsman callbacks/ 同步 Agent B 反馈到 hunter/feedback/。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from hunter.feedback.store import FEEDBACK_DIR, save_feedback_raw
from hunter.paths import PROJECT_ROOT


def resolve_callbacks_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("CRAFTSMAN_CALLBACK_DIR", "").strip()
    if env:
        return Path(env)
    return PROJECT_ROOT.parent / "craftsman" / "callbacks"


def _feedback_dest_name(data: dict[str, Any]) -> str:
    oid = data.get("opportunity_id", "unknown")
    rev = data.get("revision", 0)
    status = data.get("agent_b_status", "feedback")
    return f"{oid}_r{rev}_{status}.json"


def sync_callbacks(
    *,
    callbacks_dir: Path | None = None,
    skip_terminal: bool = True,
) -> dict[str, Any]:
    """
    将 callbacks/*.json 复制到 feedback/（已存在同名则跳过）。

    skip_terminal: 跳过 in_progress 等中间态，只同步终态反馈。
    """
    src = resolve_callbacks_dir(callbacks_dir)
    if not src.is_dir():
        return {"skipped": True, "reason": f"callbacks 目录不存在: {src}", "imported": 0}

    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    terminal = {
        "needs_clarification",
        "rejected",
        "accepted",
        "implementation_failed",
        "ready_for_release",
        "submitted",
        "platform_unavailable",
    }
    imported = 0
    skipped = 0

    for path in sorted(src.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            skipped += 1
            continue
        status = str(data.get("agent_b_status", ""))
        if skip_terminal and status not in terminal:
            skipped += 1
            continue
        dest_name = _feedback_dest_name(data)
        dest = FEEDBACK_DIR / dest_name
        if dest.is_file():
            skipped += 1
            continue
        save_feedback_raw(data, filename=dest_name)
        imported += 1

    return {
        "skipped": False,
        "callbacks_dir": str(src),
        "imported": imported,
        "skipped_count": skipped,
    }

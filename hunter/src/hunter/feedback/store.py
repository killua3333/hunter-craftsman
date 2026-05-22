"""Agent B 反馈文件的读写与归档（原样保存 Craftsman JSON）。"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hunter.paths import FEEDBACK_DIR, FEEDBACK_PROCESSED_DIR


def _slug(value: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", value.strip(), flags=re.UNICODE)
    return s[:64] or "unknown"


def save_feedback_raw(data: dict[str, Any], *, filename: str | None = None) -> Path:
    """将 Agent B 反馈 JSON 原样写入 feedback/ 目录。"""
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    if filename:
        path = FEEDBACK_DIR / filename
    else:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        oid = _slug(str(data.get("opportunity_id", "unknown")))
        rev = data.get("revision", 0)
        status = _slug(str(data.get("agent_b_status", "feedback")))
        path = FEEDBACK_DIR / f"{ts}_{oid}_r{rev}_{status}.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def list_pending_feedback() -> list[Path]:
    """列出尚未归档的反馈文件。"""
    if not FEEDBACK_DIR.is_dir():
        return []
    return sorted(p for p in FEEDBACK_DIR.glob("*.json") if p.is_file())


def load_feedback_file(path: Path) -> dict[str, Any]:
    """读取一条反馈（Craftsman 原样 JSON）。"""
    return json.loads(path.read_text(encoding="utf-8"))


def archive_feedback_batch(paths: list[Path], *, week_label: str) -> Path:
    """将已处理的反馈移至 feedback/processed/{week_label}/。"""
    dest_dir = FEEDBACK_PROCESSED_DIR / week_label
    dest_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.move(str(path), str(dest_dir / path.name))
    return dest_dir

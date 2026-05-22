"""每周批处理：归纳 Agent B 反馈，更新 specialist_learnings.md。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from hunter.config import get_chat_model, load_settings
from hunter.feedback.store import (
    archive_feedback_batch,
    list_pending_feedback,
    load_feedback_file,
)
from hunter.paths import PROMPTS_DIR, REPORTS_DIR


def _iso_week_label(when: datetime | None = None) -> str:
    dt = when or datetime.now(timezone.utc)
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8").strip()


def _split_learn_response(text: str) -> tuple[str, str]:
    marker = "---SYSTEM_SUGGESTIONS---"
    if marker in text:
        body, suggestions = text.split(marker, 1)
        return body.strip(), suggestions.strip()
    return text.strip(), ""


def run_weekly_learning(
    *,
    dry_run: bool = False,
    min_feedback_count: int | None = None,
) -> dict[str, Any]:
    """
    读取 feedback/*.json，调用模型更新 specialist_learnings.md，归档反馈。

    不自动修改 specialist_system.md；系统规则建议写入 reports/。
    """
    settings = load_settings()
    learn_cfg = settings.get("learning", {})
    min_count = (
        int(min_feedback_count)
        if min_feedback_count is not None
        else int(learn_cfg.get("min_feedback_count", 1))
    )

    pending = list_pending_feedback()
    if len(pending) < min_count:
        return {
            "skipped": True,
            "reason": f"待处理反馈 {len(pending)} 条，少于阈值 {min_count}",
            "pending_count": len(pending),
        }

    feedback_items = [load_feedback_file(p) for p in pending]
    feedback_json = "\n\n".join(
        f"### {fb.get('opportunity_id', 'unknown')}\n```json\n"
        f"{json.dumps(fb, ensure_ascii=False, indent=2)}\n```"
        for fb in feedback_items
    )

    system_path = PROMPTS_DIR / "specialist_system.md"
    learnings_path = PROMPTS_DIR / "specialist_learnings.md"
    current_system = system_path.read_text(encoding="utf-8")
    current_learnings = learnings_path.read_text(encoding="utf-8")

    editor_prompt = _load_prompt("weekly_learn")
    user_content = f"""## 当前 specialist_system.md（只读）
{current_system}

## 当前 specialist_learnings.md
{current_learnings}

## 本周 Agent B 反馈（共 {len(feedback_items)} 条）
{feedback_json}
"""

    if dry_run:
        return {
            "skipped": False,
            "dry_run": True,
            "pending_count": len(pending),
            "would_update": str(learnings_path),
        }

    model = get_chat_model()
    response = model.invoke(
        [
            SystemMessage(content=editor_prompt),
            HumanMessage(content=user_content),
        ]
    )
    raw = str(response.content)
    new_learnings, system_suggestions = _split_learn_response(raw)

    week = _iso_week_label()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"learning-{week}.md"
    suggest_path = REPORTS_DIR / f"system_suggested-{week}.md"

    backup = learnings_path.with_suffix(".md.bak")
    backup.write_text(current_learnings, encoding="utf-8")
    learnings_path.write_text(new_learnings + "\n", encoding="utf-8")

    report_path.write_text(
        f"# 每周学习报告 {week}\n\n"
        f"- 处理反馈：{len(pending)} 条\n"
        f"- 已更新：`prompts/specialist_learnings.md`\n"
        f"- 备份：`prompts/specialist_learnings.md.bak`\n\n"
        f"## 原始模型输出（含分隔符前正文）\n\n{new_learnings}\n",
        encoding="utf-8",
    )
    suggest_path.write_text(
        f"# specialist_system 升格建议（{week}，需人工审核）\n\n"
        f"{system_suggestions or '（无）'}\n",
        encoding="utf-8",
    )

    archive_dir = archive_feedback_batch(pending, week_label=week)

    return {
        "skipped": False,
        "week": week,
        "processed_count": len(pending),
        "learnings_path": str(learnings_path),
        "backup_path": str(backup),
        "report_path": str(report_path),
        "system_suggested_path": str(suggest_path),
        "archived_to": str(archive_dir),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Hunter 每周反馈学习（更新 specialist_learnings.md）")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不调用模型、不写文件")
    parser.add_argument("--min", type=int, default=None, help="最少反馈条数才执行")
    args = parser.parse_args()
    result = run_weekly_learning(dry_run=args.dry_run, min_feedback_count=args.min)
    if result.get("skipped"):
        print(result["reason"])
    elif result.get("dry_run"):
        print(f"[dry-run] 将处理 {result['pending_count']} 条反馈 → {result['would_update']}")
    else:
        print(f"已处理 {result['processed_count']} 条反馈（{result['week']}）")
        print(f"  learnings: {result['learnings_path']}")
        print(f"  report:    {result['report_path']}")
        print(f"  建议审核:  {result['system_suggested_path']}")
        print(f"  归档:      {result['archived_to']}")


if __name__ == "__main__":
    main()

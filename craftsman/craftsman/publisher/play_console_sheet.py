"""Play Console 首次建 app — 自动生成操作清单（方案 A）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from craftsman.publisher.handoff import application_id


def _category_hint(keywords: list[str]) -> str:
    blob = " ".join(keywords).lower()
    if any(k in blob for k in ("健康", "health", "fitness")):
        return "健康与健身"
    if any(k in blob for k in ("效率", "productivity", "工具", "tool")):
        return "效率工具 / 工具"
    return "工具"


def generate_play_console_sheet(
    *,
    handoff: dict[str, Any],
    workspace: Path | None = None,
    icon_path: str | None = None,
    screenshot_paths: list[str] | None = None,
    app_name: str | None = None,
) -> dict[str, Any]:
    """生成 Play Console 人工操作清单（文本 + JSON）。"""
    package = (
        application_id(handoff)
        or (handoff.get("release_bundle") or {}).get("application_id")
        or handoff.get("application_id")
        or ""
    )
    compliance = handoff.get("compliance_metadata") or {}
    if not app_name:
        app_name = compliance.get("subtitle") or package.split(".")[-1] or "App"
    keywords = list(compliance.get("keywords") or [])
    description = str(compliance.get("description") or "")
    privacy_url = str(compliance.get("privacy_url") or "")
    category = _category_hint(keywords)

    icon = icon_path or ""
    shots = screenshot_paths or []
    ws = str(workspace) if workspace else ""

    lines = [
        "═══ Play Console 操作清单 ═══",
        f"包名：{package}",
        f"应用名：{app_name}",
        f"类别：{category}",
        "",
        "描述（复制粘贴）：",
        description or "（见 play/metadata/zh-CN/description.txt）",
        "",
        f"图标路径：{icon or '(见 workspace artifacts/icon)'}",
        f"截图路径：{', '.join(shots) if shots else '(见 workspace artifacts/screenshots/)'}",
        f"隐私政策 URL：{privacy_url}",
        "",
        "数据安全表：不收集任何用户数据（纯本地 MVP 默认）",
        "内容分级：适合所有人",
        "目标受众：18 岁以上",
        "",
        "步骤：",
        "1. Play Console → 创建应用 → 包名与上表一致",
        "2. 商店设置 → 主商店信息 → 粘贴描述/图标/截图",
        "3. 政策 → 隐私政策 URL",
        "4. 数据安全 + 内容分级 + 目标受众",
        "5. Internal testing → 添加测试员 Gmail",
        "",
        "预计操作时间：约 15 分钟",
        f"工作区：{ws}",
    ]
    text = "\n".join(lines)
    payload = {
        "package_name": package,
        "app_name": app_name,
        "category": category,
        "description": description,
        "privacy_url": privacy_url,
        "icon_path": icon,
        "screenshot_paths": shots,
        "workspace": ws,
        "estimated_minutes": 15,
    }

    setup_path = None
    if workspace is not None:
        workspace.mkdir(parents=True, exist_ok=True)
        setup_path = workspace / "play_console_setup.txt"
        setup_path.write_text(text, encoding="utf-8")
        (workspace / "play_console_setup.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return {
        "text": text,
        "json": payload,
        "path": str(setup_path) if setup_path else None,
    }

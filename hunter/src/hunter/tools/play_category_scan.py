"""固定 Play 类目轮询 — Autopilot 选品辅助。"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from hunter.tools.play_search import play_search

_DEFAULT_CATEGORIES = (
    "工具 app 差评 广告",
    "效率 app 痛点",
    "健康 app 简单",
)


@tool
def play_category_scan(max_per_category: int = 2) -> str:
    """轮询工具/效率/健康等高价值 Play 类目，汇总竞品与痛点线索。

    适用：autopilot 自动发现；无需用户指定具体 app 名称。

    参数：
    - max_per_category: 每个类目最多取几条结果，1～5，默认 2
    """
    max_per_category = max(1, min(int(max_per_category), 5))
    combined: list[dict] = []
    for query in _DEFAULT_CATEGORIES:
        raw = play_search.invoke({"query": query, "max_results": max_per_category})
        payload = json.loads(raw)
        if payload.get("error"):
            continue
        for row in payload.get("results") or []:
            combined.append(
                {
                    "category_query": query,
                    "title": row.get("title"),
                    "url": row.get("url"),
                    "snippet": row.get("snippet"),
                }
            )
    return json.dumps(
        {
            "categories_scanned": list(_DEFAULT_CATEGORIES),
            "result_count": len(combined),
            "results": combined,
        },
        ensure_ascii=False,
        indent=2,
    )

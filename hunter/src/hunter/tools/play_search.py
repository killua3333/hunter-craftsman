"""Google Play 机会轻量搜索 — 基于 Tavily + site:play.google.com。"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from hunter.tools.tavily_search import _format_search_response, _get_client


@tool
def play_search(
    query: str,
    max_results: int = 5,
) -> str:
    """在 Google Play 相关页面中搜索 Android 工具类 app 机会与竞品痛点。

    适用：autopilot 自动发现需求；无需用户提供具体 app 名称。

    参数：
    - query: 检索词，如「番茄钟」「单位换算」「广告太多 差评」
    - max_results: 1～8，默认 5

    返回 JSON（含 title/url/snippet），供写入 evidence 并选定机会。
    """
    query = query.strip()
    if not query:
        return json.dumps({"error": "query 不能为空"}, ensure_ascii=False)

    max_results = max(1, min(int(max_results), 8))
    play_query = f"site:play.google.com {query} app"
    response = _get_client().search(
        query=play_query,
        max_results=max_results,
        topic="general",
        search_depth="basic",
        include_answer=True,
    )
    payload = json.loads(_format_search_response(response))
    payload["play_search_query"] = play_query
    return json.dumps(payload, ensure_ascii=False, indent=2)

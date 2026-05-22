"""Tavily 网页搜索 — 市场调研与热点检索。"""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from langchain_core.tools import tool

Topic = Literal["general", "news", "finance"]
TimeRange = Literal["", "day", "week", "month", "year"]
SearchDepth = Literal["basic", "advanced", "fast", "ultra-fast"]


def _get_api_key() -> str:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "未设置 TAVILY_API_KEY。请在 .env 中配置，密钥见 https://tavily.com"
        )
    return key


def _get_client():
    from tavily import TavilyClient

    return TavilyClient(api_key=_get_api_key())


def _format_search_response(response: dict[str, Any]) -> str:
    items = []
    for i, row in enumerate(response.get("results") or [], start=1):
        content = row.get("content") or ""
        items.append(
            {
                "rank": i,
                "title": row.get("title") or "",
                "url": row.get("url") or "",
                "snippet": content[:800] + ("…" if len(content) > 800 else ""),
                "score": row.get("score"),
            }
        )
    return json.dumps(
        {
            "query": response.get("query"),
            "answer": response.get("answer"),
            "result_count": len(items),
            "results": items,
        },
        ensure_ascii=False,
        indent=2,
    )


@tool
def web_search(
    query: str,
    max_results: int = 5,
    topic: Topic = "general",
    time_range: TimeRange = "",
    search_depth: SearchDepth = "basic",
) -> str:
    """使用 Tavily 检索互联网上的市场信息、竞品、用户痛点与趋势。

    适用：App 品类调研、关键词热度、竞品动态、媒体报道、社区讨论。

    参数：
    - query: 检索词，建议含品类+「痛点/差评/需求/趋势」，如「计算器 app 用户 差评 广告」
    - max_results: 1～10，默认 5
    - topic: general | news | finance
    - time_range: 留空或 day/week/month/year
    - search_depth: basic（默认）| advanced | fast | ultra-fast

    返回 JSON 字符串（含 answer 摘要与 results 列表的 title/url/snippet）。
    """
    query = query.strip()
    if not query:
        return json.dumps({"error": "query 不能为空"}, ensure_ascii=False)

    max_results = max(1, min(int(max_results), 10))
    kwargs: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "topic": topic,
        "search_depth": search_depth,
        "include_answer": True,
    }
    if time_range:
        kwargs["time_range"] = time_range

    response = _get_client().search(**kwargs)
    return _format_search_response(response)

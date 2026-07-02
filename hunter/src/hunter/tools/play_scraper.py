"""Google Play Store 真实数据检索 — 基于 google-play-scraper。

提供三个 LangChain tool，供 Agent A 的 ReAct agent 直接调用：
  play_search_apps   — 按关键词/类目搜索 Play Store 应用列表
  play_get_reviews   — 读取指定 app 的真实用户评论
  play_get_app_detail — 读取单个 app 的完整元数据
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from langchain_core.tools import tool
except ModuleNotFoundError:
    class _LocalTool:
        def __init__(self, fn):
            self.fn = fn
            self.__name__ = getattr(fn, "__name__", "local_tool")
            self.__doc__ = getattr(fn, "__doc__", None)

        def __call__(self, *args, **kwargs):
            return self.fn(*args, **kwargs)

        def invoke(self, payload):
            if isinstance(payload, dict):
                return self.fn(**payload)
            return self.fn(payload)

    def tool(fn):
        return _LocalTool(fn)


def _ensure_play_proxy() -> None:
    """确保 google-play-scraper（基于 urllib）能通过代理连接 Google Play。

    google-play-scraper 内部使用 urllib.request.urlopen，不会自动读取
    系统代理设置。需要显式设置 HTTPS_PROXY 环境变量。
    """
    for key in ("HTTPS_PROXY", "HTTP_PROXY"):
        val = os.environ.get(key, "").strip()
        if val:
            return
    # .env 中配置的代理也需要被识别
    candidates = ["http://127.0.0.1:10808", "socks5://127.0.0.1:10808"]
    for c in candidates:
        os.environ.setdefault("HTTPS_PROXY", c)
        os.environ.setdefault("HTTP_PROXY", c)


# google-play-scraper 常量
PLAY_COLLECTIONS = frozenset({
    "TOP_FREE", "TOP_PAID", "GROSSING",
    "TOP_FREE_GAMES", "TOP_PAID_GAMES", "TOP_GROSSING_GAMES",
    "TRENDING", "TOP_SELLING", "NEW_FREE", "NEW_PAID",
    "NEW_FREE_GAMES", "NEW_PAID_GAMES",
})

PLAY_CATEGORIES = frozenset({
    "APPLICATION", "ANDROID_WEAR", "ART_AND_DESIGN", "AUTO_AND_VEHICLES",
    "BEAUTY", "BOOKS_AND_REFERENCE", "BUSINESS", "COMICS", "COMMUNICATION",
    "DATING", "EDUCATION", "ENTERTAINMENT", "EVENTS", "FINANCE",
    "FOOD_AND_DRINK", "HEALTH_AND_FITNESS", "HOUSE_AND_HOME",
    "LIBRARIES_AND_DEMO", "LIFESTYLE", "MAPS_AND_NAVIGATION",
    "MEDICAL", "MUSIC_AND_AUDIO", "NEWS_AND_MAGAZINES", "PARENTING",
    "PERSONALIZATION", "PHOTOGRAPHY", "PRODUCTIVITY", "SHOPPING",
    "SOCIAL", "SPORTS", "TOOLS", "TRAVEL_AND_LOCAL", "VIDEO_PLAYERS",
    "WEATHER", "GAME",
})


def _safe_str(value: Any, max_len: int = 400) -> str:
    s = str(value or "")
    return s[:max_len] + "\u2026" if len(s) > max_len else s


def _compact_app(item: dict) -> dict[str, Any]:
    """将 google-play-scraper 返回的 app dict 精简为 Agent 可用的字段。"""
    return {
        "appId": item.get("appId"),
        "title": item.get("title"),
        "developer": item.get("developer"),
        "score": item.get("score"),
        "ratings": item.get("ratings"),
        "installs": item.get("installs"),
        "free": item.get("free"),
        "price": item.get("price"),
        "genre": item.get("genre"),
        "icon": item.get("icon"),
        "url": item.get("url"),
        "summary": _safe_str(item.get("summary") or ""),
        "updated": item.get("updated"),
    }


@tool
def play_search_apps(
    query: str = "",
    category: str = "",
    collection: str = "",
    count: int = 10,
    page: int = 0,
) -> str:
    """在 Google Play Store 中搜索应用，返回真实 app 列表（含 appId、评分、下载量、免费/付费等）。

    参数：
    - query: 关键词（如「番茄钟」「单位换算」），留空则按 collection 取榜单
    - category: 类目，如 TOOLS / PRODUCTIVITY / HEALTH_AND_FITNESS；留空不限制
    - collection: 榜单，如 TOP_FREE / NEW_FREE / TRENDING；与 query 互斥（有 query 时忽略）
    - count: 返回条数（1～20，默认 10）
    - page: 第几页（0 起始），与 count 配合翻页

    返回 JSON（results 数组含 appId/title/developer/score/ratings/installs/free/genre/summary）。
    """
    _ensure_play_proxy()
    try:
        return _play_search_apps_impl(query, category, collection, count, page)
    except Exception as exc:
        return json.dumps({"error": f"Play Store 搜索失败: {exc}", "query": query.strip() or collection.strip().upper()},
                          ensure_ascii=False)


def _play_search_apps_impl(query, category, collection, count, page):
    import google_play_scraper

    count = max(1, min(int(count), 20))

    cat = category.strip().upper() if category.strip() else None
    if cat and cat not in PLAY_CATEGORIES:
        cat = None

    if query.strip():
        results = google_play_scraper.search(
            query.strip(),
            lang="en",
            country="us",
            n_hits=count,
        )
    elif collection.strip().upper() in PLAY_COLLECTIONS:
        results = google_play_scraper.collection(
            collection=collection.strip().upper(),
            category=cat,
            lang="en",
            country="us",
        )
        results = results[:count]
    else:
        return json.dumps({"error": "请提供 query 或有效的 collection（如 TOP_FREE）"}, ensure_ascii=False)

    apps = [_compact_app(a) for a in results[:count]]
    return json.dumps(
        {
            "query": query.strip() or collection.strip().upper(),
            "category": cat or "any",
            "result_count": len(apps),
            "results": apps,
        },
        ensure_ascii=False,
        indent=2,
    )


@tool
def play_get_reviews(
    app_id: str,
    count: int = 10,
    sort: str = "most_relevant",
) -> str:
    """读取 Google Play 中指定 app 的真实用户评论。

    参数：
    - app_id: Play Store 的 appId（如 com.example.app），必须提供
    - count: 返回条数（1～30，默认 10）
    - sort: 排序方式 — most_relevant（默认）| newest | rating

    返回 JSON（含 userName、score、content、thumbsUpCount、at 等）。
    """
    _ensure_play_proxy()
    try:
        import google_play_scraper

        if not app_id.strip():
            return json.dumps({"error": "app_id 不能为空"}, ensure_ascii=False)

        count = max(1, min(int(count), 30))
        sort_mode = sort.strip().lower()
        if sort_mode not in ("most_relevant", "newest", "rating"):
            sort_mode = "most_relevant"

        if sort_mode == "newest":
            scraper_sort = google_play_scraper.Sort.NEWEST
        elif sort_mode == "rating":
            scraper_sort = google_play_scraper.Sort.RATING
        else:
            scraper_sort = google_play_scraper.Sort.MOST_RELEVANT

        result, _ = google_play_scraper.reviews(
            app_id.strip(),
            lang="en",
            country="us",
            sort=scraper_sort,
            count=count,
        )

        reviews = []
        for r in result[:count]:
            reviews.append({
                "userName": r.get("userName"),
                "score": r.get("score"),
                "content": _safe_str(r.get("content") or "", 500),
                "thumbsUpCount": r.get("thumbsUpCount"),
                "at": str(r.get("at")) if r.get("at") else None,
            })

        return json.dumps(
            {
                "app_id": app_id.strip(),
                "sort": sort_mode,
                "result_count": len(reviews),
                "reviews": reviews,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"error": f"Play Store 评论获取失败: {exc}", "app_id": app_id.strip()},
                          ensure_ascii=False)


@tool
def play_get_app_detail(app_id: str) -> str:
    """读取 Google Play 中单个 app 的完整元数据。

    参数：
    - app_id: Play Store 的 appId（如 com.example.app），必须提供

    返回 JSON（含 title/developer/score/ratings/installs/updated/genre/description/changelog 等）。
    """
    _ensure_play_proxy()
    try:
        import google_play_scraper

        if not app_id.strip():
            return json.dumps({"error": "app_id 不能为空"}, ensure_ascii=False)

        result = google_play_scraper.app(
            app_id.strip(),
            lang="en",
            country="us",
        )

        return json.dumps(
            {
                "appId": result.get("appId"),
                "title": result.get("title"),
                "developer": result.get("developer"),
                "developerWebsite": result.get("developerWebsite"),
                "score": result.get("score"),
                "ratings": result.get("ratings"),
                "reviews": result.get("reviews"),
                "installs": result.get("installs"),
                "free": result.get("free"),
                "price": result.get("price"),
                "genre": result.get("genre"),
                "updated": result.get("updated"),
                "version": result.get("version"),
                "contentRating": result.get("contentRating"),
                "description": _safe_str(result.get("description") or "", 800),
                "recentChanges": _safe_str(result.get("recentChanges") or "", 300),
                "icon": result.get("icon"),
                "url": result.get("url"),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"error": f"Play Store 详情获取失败: {exc}", "app_id": app_id.strip()},
                          ensure_ascii=False)


@tool
def play_analyze_reviews(
    app_id: str,
    max_reviews: int = 100,
) -> str:
    """批量抓取指定 app 的低分差评（score <= 3），并对痛点进行主题聚类分析。

    这个工具会自动做两件事：
    1. 抓取该 app 最多 max_reviews 条差评
    2. 对差评内容进行主题聚类，输出痛点频率、典型原文、用户期望

    参数：
    - app_id: Play Store 的 appId（如 com.example.app），必须提供
    - max_reviews: 最多抓取的差评数量（默认 100，上限 200）

    返回 JSON（含 pain_points、review_samples、feature_requests）。
    """
    from collections import Counter
    import re

    _ensure_play_proxy()
    try:
        import google_play_scraper

        if not app_id.strip():
            return json.dumps({"error": "app_id 不能为空"}, ensure_ascii=False)

        max_reviews = max(10, min(int(max_reviews), 200))

        # 分多次抓取差评（每次最多 200 条，但评分过滤需要手动筛选）
        all_reviews: list[dict] = []
        continuation_token = None
        batches = 0
        while len(all_reviews) < max_reviews and batches < 5:
            result, continuation_token = google_play_scraper.reviews(
                app_id.strip(),
                lang="en",
                country="us",
                sort=google_play_scraper.Sort.MOST_RELEVANT,
                count=min(200, max_reviews * 2),
                continuation_token=continuation_token,
            )
            # 只保留低分差评
            for r in result:
                score = r.get("score", 0)
                if score is not None and score <= 3:
                    all_reviews.append({
                        "score": score,
                        "content": (r.get("content") or "").strip(),
                        "thumbsUpCount": r.get("thumbsUpCount", 0),
                        "at": str(r.get("at")) if r.get("at") else None,
                    })
            if not continuation_token:
                break
            batches += 1

        all_reviews = all_reviews[:max_reviews]

        if not all_reviews:
            return json.dumps({
                "app_id": app_id.strip(),
                "total_low_score_reviews": 0,
                "pain_points": [],
                "review_samples": [],
                "feature_requests": [],
                "summary": "该 app 没有足够的低分差评（用户满意度可能较高）",
            }, ensure_ascii=False, indent=2)

        # ---- 本地关键词聚类（不依赖 LLM，工具内完成） ----
        # 常见痛点关键词映射
        PAIN_KEYWORDS = [
            ("广告", ["ad", "ads", "advertisement", "广告", "광고"]),
            ("崩溃/闪退", ["crash", "crashes", "crashing", "freeze", "froze", "freezes", "闪退", "崩溃"]),
            ("订阅/付费", ["subscription", "pay", "paid", "premium", "charge", "money", "expensive", "付费", "订阅", "收费"]),
            ("权限过多", ["permission", "permissions", "privacy", "tracking", "data", "权限", "隐私"]),
            ("界面复杂", ["confusing", "complicated", "complex", "cluttered", "messy", "unintuitive", "混乱", "复杂"]),
            ("功能缺失", ["missing", "lack", "need", "should have", "wish", "希望", "缺少", "没有"]),
            ("卡顿/慢", ["slow", "lag", "laggy", "lagging", "sluggish", "卡", "慢"]),
            ("电量消耗", ["battery", "drain", "power", "耗电", "费电"]),
            ("无法编辑", ["edit", "editing", "modify", "change", "undo", "编辑", "修改"]),
            ("同步问题", ["sync", "backup", "restore", "lost", "lose", "同步", "备份", "丢失"]),
            ("通知骚扰", ["notification", "notifications", "spam", "通知", "骚扰"]),
            ("长期未更新", ["outdated", "abandoned", "no update", "broken", "不再更新"]),
        ]

        # 统计每个痛点的出现次数和相关评论
        pain_stats: dict[str, list[dict]] = {}
        for r in all_reviews:
            content_lower = r["content"].lower()
            for label, keywords in PAIN_KEYWORDS:
                for kw in keywords:
                    if kw in content_lower:
                        if label not in pain_stats:
                            pain_stats[label] = []
                        pain_stats[label].append(r)
                        break

        total = len(all_reviews)
        pain_points = []
        for label, reviews in sorted(pain_stats.items(), key=lambda x: -len(x[1])):
            pct = round(len(reviews) / total * 100, 1)
            # 取 3 条典型评论
            samples = sorted(reviews, key=lambda x: x.get("thumbsUpCount", 0) or 0, reverse=True)[:3]
            pain_points.append({
                "theme": label,
                "frequency_pct": pct,
                "review_count": len(reviews),
                "typical_reviews": [
                    {"score": s.get("score"), "content": _safe_str(s.get("content") or "", 300)}
                    for s in samples
                ],
            })

        # 提取功能期望（含 "should"/"need"/"wish"/"希望" 等关键词的评论）
        want_keywords = ["should", "need", "wish", "hopefully", "please add", "希望", "要是", "如果能"]
        feature_requests = []
        for r in all_reviews:
            content = r["content"].lower()
            if any(kw in content for kw in want_keywords):
                feature_requests.append({
                    "score": r["score"],
                    "content": _safe_str(r.get("content") or "", 300),
                    "thumbsUpCount": r.get("thumbsUpCount", 0),
                })
        # 按点赞数排序
        feature_requests.sort(key=lambda x: x.get("thumbsUpCount", 0) or 0, reverse=True)
        feature_requests = feature_requests[:10]

        return json.dumps({
            "app_id": app_id.strip(),
            "total_low_score_reviews": total,
            "pain_points": pain_points,
            "feature_requests": feature_requests,
            "summary": (
                f"共分析 {total} 条低分差评（score <= 3）。"
                f"主要痛点：{', '.join(p['theme'] for p in pain_points[:5])}。"
                f"用户期望功能：{len(feature_requests)} 条相关评论。"
            ),
        }, ensure_ascii=False, indent=2)

    except Exception as exc:
        return json.dumps({"error": f"差评分析失败: {exc}", "app_id": app_id.strip()},
                          ensure_ascii=False)


@tool
def play_competitive_analysis(
    query: str,
    count: int = 10,
) -> str:
    """对 Google Play Store 中某个品类的竞品做快速横向对比分析。

    自动完成：
    1. 按关键词搜索 count 个 app
    2. 对每个 app 调用 play_get_app_detail 获取元数据
    3. 汇总为对比表，自动标记 stale（超过 1 年未更新）、ripe（高安装量 + 低评分 + stale）

    参数：
    - query: 品类关键词（如 "calculator", "pomodoro timer", "unit converter"）
    - count: 对比的 app 数量（1-15，默认 10）

    返回 JSON（含 competitive_matrix, ripe_opportunities, summary）。
    """
    import time

    _ensure_play_proxy()
    try:
        import google_play_scraper
        from datetime import datetime, timezone

        count = max(1, min(int(count), 15))

        # 1. 搜索
        try:
            search_results = google_play_scraper.search(query.strip(), lang="en", country="us", n_hits=count)
        except Exception:
            return json.dumps({"error": f"搜索失败: {query}", "query": query.strip()}, ensure_ascii=False)

        # 2. 取每个 app 的详情
        competitive_matrix = []
        for item in search_results[:count]:
            app_id = item.get("appId")
            if not app_id:
                continue
            try:
                detail = google_play_scraper.app(app_id, lang="en", country="us")
            except Exception:
                detail = {}
            # 收集信息
            updated_str = str(detail.get("updated") or item.get("updated") or "")
            stale = False
            try:
                # 解析 ISO 日期
                updated_date = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                months_since_update = (datetime.now(timezone.utc) - updated_date).days / 30
                stale = months_since_update > 12
            except Exception:
                pass

            score = detail.get("score") or item.get("score") or 0
            installs_str = str(detail.get("installs") or item.get("installs") or "0")
            # 解析安装量（如 "1,000,000+"）
            try:
                installs_num = int(installs_str.replace(",", "").replace("+", "").replace(" ", ""))
            except Exception:
                installs_num = 0

            ripe = bool(installs_num >= 100000 and score < 3.8 and stale)

            competitive_matrix.append({
                "appId": app_id,
                "title": detail.get("title") or item.get("title", ""),
                "developer": detail.get("developer") or item.get("developer", ""),
                "score": score,
                "ratings": detail.get("ratings"),
                "installs": installs_str,
                "free": detail.get("free", True),
                "genre": detail.get("genre") or item.get("genre", ""),
                "updated": updated_str,
                "stale": stale,
                "ripe": ripe,
            })
            time.sleep(0.5)  # 节制请求频率

        ripe_opportunities = [m for m in competitive_matrix if m.get("ripe")]
        # 按安装量排序 ripe 机会
        ripe_opportunities.sort(key=lambda m: str(m.get("installs", "")), reverse=True)

        return json.dumps({
            "query": query.strip(),
            "result_count": len(competitive_matrix),
            "competitive_matrix": competitive_matrix,
            "ripe_opportunities": ripe_opportunities,
            "summary": (
                f"扫描 {query} 品类共 {len(competitive_matrix)} 个 app。"
                f"发现 {len(ripe_opportunities)} 个 ripe 机会（高安装量 + 低评分 + 超过1年未更新）。"
            ),
        }, ensure_ascii=False, indent=2)

    except Exception as exc:
        return json.dumps({"error": f"竞品分析失败: {exc}", "query": query.strip()},
                          ensure_ascii=False)

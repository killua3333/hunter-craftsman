from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

DEFAULT_SEED_QUERIES = [
    "simple timer",
    "checklist app",
    "unit converter",
    "habit tracker",
    "expense tracker",
    "water reminder",
]

play_competitive_analysis: Any | None = None
play_analyze_reviews: Any | None = None
DiscoveryEventSink = Callable[[str, str, dict[str, Any]], None]


def build_play_discovery_run(
    *,
    seed_queries: list[str] | None = None,
    competitors_per_query: int = 5,
    reviews_per_app: int = 30,
    event_sink: DiscoveryEventSink | None = None,
) -> dict[str, Any]:
    """Run real Google Play discovery and stream observable progress events."""

    def emit(stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
        if event_sink is not None:
            event_sink(stage, message, payload or {})

    queries = [q.strip() for q in (seed_queries or DEFAULT_SEED_QUERIES) if q.strip()]
    run_id = "disc-" + uuid4().hex[:10]
    competitor_matrix: list[dict[str, Any]] = []
    low_score_reviews: list[dict[str, Any]] = []
    pain_clusters: dict[str, int] = {}
    candidates: list[dict[str, Any]] = []

    emit(
        "checking_environment",
        "\u6b63\u5728\u68c0\u67e5\u5e94\u7528\u5546\u5e97\u91c7\u96c6\u5de5\u5177\u548c\u7f51\u7edc\u4ee3\u7406\u3002",
        {
            "seed_query_count": len(queries),
            "has_proxy": _has_proxy_env(),
            "proxy_keys": [key for key in ("HTTPS_PROXY", "HTTP_PROXY") if os.environ.get(key)],
        },
    )
    try:
        competitive_tool, reviews_tool = _play_tools()
    except ModuleNotFoundError as exc:
        emit(
            "dependency_missing",
            "\u7f3a\u5c11\u5e94\u7528\u5546\u5e97\u91c7\u96c6\u4f9d\u8d56\uff0c\u65e0\u6cd5\u5f00\u59cb\u771f\u5b9e\u641c\u7d22\u3002",
            {"missing_module": exc.name or str(exc)},
        )
        raise
    emit("play_tools_loaded", "\u5e94\u7528\u5546\u5e97\u91c7\u96c6\u5de5\u5177\u5df2\u52a0\u8f7d\uff0c\u51c6\u5907\u6309\u5173\u952e\u8bcd\u641c\u7d22\u3002", {"has_proxy": _has_proxy_env()})

    for query in queries:
        emit(
            "searching_query",
            f"\u6b63\u5728\u641c\u7d22\u5173\u952e\u8bcd\uff1a{query}",
            {"query": query, "competitors_per_query": competitors_per_query},
        )
        competitive = _json_tool(competitive_tool.invoke({"query": query, "count": competitors_per_query}))
        if competitive.get("error"):
            emit(
                "query_search_failed",
                f"\u5173\u952e\u8bcd\u201c{query}\u201d\u641c\u7d22\u5931\u8d25\u3002",
                {"query": query, "error": competitive.get("error"), "raw": competitive.get("raw")},
            )
            continue

        matrix = competitive.get("competitive_matrix") or []
        for app in matrix:
            app["seed_query"] = query
            competitor_matrix.append(app)
        emit(
            "query_search_complete",
            f"\u5173\u952e\u8bcd\u201c{query}\u201d\u8fd4\u56de {len(matrix)} \u4e2a\u53ef\u5206\u6790\u7ade\u54c1\u3002",
            {"query": query, "competitor_count": len(matrix), "apps": matrix[:5]},
        )

        selected_apps = _select_review_targets(matrix)
        emit(
            "scanning_competitors",
            f"\u5df2\u9009\u51fa {len(selected_apps)} \u4e2a\u91cd\u70b9\u7ade\u54c1\u8bfb\u53d6\u4f4e\u5206\u8bc4\u8bba\u3002",
            {"query": query, "review_target_count": len(selected_apps), "apps": selected_apps[:5]},
        )
        query_reviews = []
        if reviews_per_app <= 0:
            emit(
                "reviews_skipped",
                f"\u5173\u952e\u8bcd\u201c{query}\u201d\u672c\u8f6e\u672a\u8bfb\u53d6\u8bc4\u8bba\u3002",
                {"query": query, "reason": "reviews_per_app is 0"},
            )
        else:
            for app in selected_apps:
                app_id = str(app.get("appId") or "")
                if not app_id:
                    continue
                title = app.get("title") or app_id
                emit(
                    "fetching_reviews",
                    f"\u6b63\u5728\u8bfb\u53d6\u7ade\u54c1\u201c{title}\u201d\u7684\u4f4e\u5206\u8bc4\u8bba\u3002",
                    {"query": query, "app_id": app_id, "app_title": app.get("title"), "reviews_per_app": reviews_per_app},
                )
                review_payload = _json_tool(reviews_tool.invoke({"app_id": app_id, "max_reviews": reviews_per_app}))
                review_payload["seed_query"] = query
                review_payload["app_title"] = app.get("title")
                if review_payload.get("error"):
                    emit(
                        "review_fetch_failed",
                        f"\u7ade\u54c1\u201c{title}\u201d\u8bc4\u8bba\u8bfb\u53d6\u5931\u8d25\u3002",
                        {"query": query, "app_id": app_id, "app_title": app.get("title"), "error": review_payload.get("error")},
                    )
                    continue
                low_score_reviews.append(review_payload)
                query_reviews.append(review_payload)
                for pain in review_payload.get("pain_points") or []:
                    theme = str(pain.get("theme") or "").strip()
                    if theme:
                        pain_clusters[theme] = pain_clusters.get(theme, 0) + int(pain.get("review_count") or 0)
                emit(
                    "reviews_complete",
                    f"\u7ade\u54c1\u201c{title}\u201d\u8bfb\u53d6\u5230 {int(review_payload.get('total_low_score_reviews') or 0)} \u6761\u4f4e\u5206\u8bc4\u8bba\u3002",
                    {
                        "query": query,
                        "app_id": app_id,
                        "app_title": app.get("title"),
                        "low_score_review_count": int(review_payload.get("total_low_score_reviews") or 0),
                        "pain_point_count": len(review_payload.get("pain_points") or []),
                    },
                )

        if not matrix:
            emit("query_no_competitors", f"\u5173\u952e\u8bcd\u201c{query}\u201d\u6ca1\u6709\u8fd4\u56de\u53ef\u5206\u6790\u7ade\u54c1\u3002", {"query": query})
            continue
        candidate = _candidate_from_query(query, matrix, query_reviews)
        candidates.append(candidate)
        emit(
            "candidate_scored",
            f"\u5173\u952e\u8bcd\u201c{query}\u201d\u5df2\u5f62\u6210\u5019\u9009\u8bc4\u5206\uff1a\u673a\u4f1a {candidate.get('opportunity_score')}\uff0c\u9002\u914d {candidate.get('build_fit_score')}\uff0c\u8bc1\u636e {candidate.get('evidence_score')}\u3002",
            {"query": query, "candidate": candidate},
        )

    candidates = sorted(candidates, key=lambda item: item.get("opportunity_score") or 0, reverse=True)
    emit("scoring_candidates", f"\u5df2\u5b8c\u6210 {len(candidates)} \u4e2a\u5019\u9009\u65b9\u5411\u7684\u6392\u5e8f\u3002", {"candidate_count": len(candidates), "candidate_names": [c.get("name") for c in candidates[:8]]})
    selected = candidates[0] if candidates else {}
    rejected = [
        {
            "name": item.get("name"),
            "niche": item.get("niche"),
            "reason": item.get("rejection_reason") or "score below selected candidate",
            "opportunity_score": item.get("opportunity_score"),
            "build_fit_score": item.get("build_fit_score"),
        }
        for item in candidates[1:6]
    ]
    return {
        "discovery_run_id": run_id,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "seed_queries": queries,
        "searched_apps": competitor_matrix,
        "competitor_matrix": competitor_matrix,
        "low_score_reviews": low_score_reviews,
        "pain_point_clusters": [
            {"theme": theme, "review_count": count}
            for theme, count in sorted(pain_clusters.items(), key=lambda item: item[1], reverse=True)
        ],
        "candidate_opportunities": candidates,
        "rejected_candidates": rejected,
        "final_selected_opportunity": selected,
        "data_quality": _data_quality(competitor_matrix, low_score_reviews),
    }


def discovery_run_to_prompt(run: dict[str, Any]) -> str:
    compact = {
        "discovery_run_id": run.get("discovery_run_id"),
        "seed_queries": run.get("seed_queries"),
        "pain_point_clusters": run.get("pain_point_clusters")[:8],
        "candidate_opportunities": run.get("candidate_opportunities")[:6],
        "rejected_candidates": run.get("rejected_candidates")[:5],
        "final_selected_opportunity": run.get("final_selected_opportunity"),
        "data_quality": run.get("data_quality"),
    }
    return (
        "\u4ee5\u4e0b\u662f Google Play \u53ef\u76d1\u63a7\u91c7\u96c6\u6d41\u6c34\u7ebf\u4ea7\u51fa\u7684\u9700\u6c42\u5019\u9009\u3002"
        "\u4f60\u53ea\u80fd\u4ece candidate_opportunities \u4e2d\u9009\u62e9\u6700\u7ec8\u9700\u6c42\uff0c\u5e76\u5fc5\u987b\u4fdd\u7559 discovery_run_id\u3001"
        "source_apps\u3001review_pain_summary\u3001evidence_score\u3002\n\n"
        + json.dumps(compact, ensure_ascii=False, indent=2)
    )


def _play_tools() -> tuple[Any, Any]:
    global play_competitive_analysis, play_analyze_reviews
    if play_competitive_analysis is None or play_analyze_reviews is None:
        try:
            from hunter.tools.play_scraper import (
                play_analyze_reviews as _play_analyze_reviews,
                play_competitive_analysis as _play_competitive_analysis,
            )
        except ModuleNotFoundError as exc:
            if exc.name != "langchain_core":
                raise
            import importlib.util
            from pathlib import Path

            scraper_path = Path(__file__).resolve().parents[1] / "tools" / "play_scraper.py"
            spec = importlib.util.spec_from_file_location("hunter_play_scraper_direct", scraper_path)
            if spec is None or spec.loader is None:
                raise
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _play_analyze_reviews = module.play_analyze_reviews
            _play_competitive_analysis = module.play_competitive_analysis

        play_competitive_analysis = _play_competitive_analysis
        play_analyze_reviews = _play_analyze_reviews
    return play_competitive_analysis, play_analyze_reviews


def _json_tool(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        payload = json.loads(str(raw))
    except Exception as exc:
        return {"error": str(exc), "raw": str(raw)[:500]}
    return payload if isinstance(payload, dict) else {"raw": payload}


def _has_proxy_env() -> bool:
    return any(bool(os.environ.get(key, "").strip()) for key in ("HTTPS_PROXY", "HTTP_PROXY"))


def _select_review_targets(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored = sorted(
        matrix,
        key=lambda app: (
            bool(app.get("ripe")),
            _install_num(app.get("installs")),
            -(float(app.get("score") or 5)),
        ),
        reverse=True,
    )
    return scored[:2]


def _candidate_from_query(query: str, matrix: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> dict[str, Any]:
    source_apps = matrix[:5]
    total_low_reviews = sum(int(r.get("total_low_score_reviews") or 0) for r in reviews)
    pain_summary = []
    for payload in reviews:
        for pain in payload.get("pain_points") or []:
            pain_summary.append(
                {
                    "app_id": payload.get("app_id"),
                    "app_title": payload.get("app_title"),
                    "theme": pain.get("theme"),
                    "frequency_pct": pain.get("frequency_pct"),
                    "review_count": pain.get("review_count"),
                }
            )
    max_installs = max((_install_num(app.get("installs")) for app in matrix), default=0)
    stale_count = sum(1 for app in matrix if app.get("stale"))
    low_score_count = sum(1 for app in matrix if float(app.get("score") or 5) < 3.8)
    evidence_score = min(100, 35 + len(matrix) * 5 + min(total_low_reviews, 40))
    opportunity_score = min(100, 35 + min(max_installs // 100000, 25) + stale_count * 8 + low_score_count * 6 + min(total_low_reviews, 20))
    build_fit_score = _build_fit_score(query, pain_summary)
    top_pains = [str(p.get("theme")) for p in pain_summary[:3] if p.get("theme")]
    return {
        "name": f"{query.title()} MVP",
        "niche": query,
        "target_users": f"Users looking for a simpler {query} app",
        "pain_points": top_pains,
        "competitor_gap": ", ".join(top_pains) if top_pains else "competitor reviews show room for a simpler local-first app",
        "source_apps": source_apps,
        "review_pain_summary": pain_summary[:10],
        "evidence_score": evidence_score,
        "opportunity_score": opportunity_score,
        "build_fit_score": build_fit_score,
        "decision_reason": "selected from Google Play competitors and low-score review pain points",
        "rejection_reason": "lower opportunity/build fit score",
    }


def _build_fit_score(query: str, pain_summary: list[dict[str, Any]]) -> int:
    text = (query + " " + " ".join(str(p.get("theme") or "") for p in pain_summary)).lower()
    score = 82
    for token in ("sync", "account", "subscription", "cloud", "social", "payment"):
        if token in text:
            score -= 12
    for token in ("timer", "checklist", "converter", "tracker", "reminder", "calculator"):
        if token in text:
            score += 4
    return max(20, min(100, score))


def _install_num(value: Any) -> int:
    try:
        return int(str(value or "0").replace(",", "").replace("+", "").replace(" ", ""))
    except Exception:
        return 0


def _data_quality(apps: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> str:
    if apps and any(int(r.get("total_low_score_reviews") or 0) > 0 for r in reviews):
        return "measured"
    if apps:
        return "mixed"
    return "assumption"

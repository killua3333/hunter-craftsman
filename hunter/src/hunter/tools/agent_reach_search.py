"""Multi-platform discovery search powered by installed Agent Reach channels."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from langchain_core.tools import tool


AGENT_REACH_EXE = r"C:\Users\31882\.agent-reach-venv\Scripts\agent-reach.exe"
DEFAULT_TIMEOUT_SECONDS = 20


def _run_command(command: list[str], *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"exit={completed.returncode}"
        raise RuntimeError(detail)
    return completed.stdout.strip()


def _safe_call(source: str, command: list[str], *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    try:
        output = _run_command(command, timeout=timeout)
        return {
            "source": source,
            "status": "ok",
            "command": command,
            "summary": output[:1200],
        }
    except Exception as exc:
        return {
            "source": source,
            "status": "error",
            "command": command,
            "summary": str(exc)[:500],
        }


def _doctor_text() -> str:
    try:
        return _run_command([AGENT_REACH_EXE, "doctor"], timeout=30)
    except Exception:
        return ""


def _channel_enabled(doctor_text: str, label: str) -> bool:
    return label in doctor_text


def _build_queries(topic: str, doctor_text: str) -> list[tuple[str, list[str]]]:
    normalized = topic.strip()
    if not normalized:
        raise ValueError("topic 不能为空")
    escaped = normalized.replace(" ", "+")
    queries: list[tuple[str, list[str]]] = [
        ("github", ["gh", "search", "repos", normalized, "--limit", "5"]),
        (
            "web",
            ["curl.exe", "-s", f"https://r.jina.ai/http://https://www.google.com/search?q={escaped}"],
        ),
    ]
    if _channel_enabled(doctor_text, "V2EX"):
        queries.append(
            (
                "v2ex_hot",
                ["curl.exe", "-s", "https://r.jina.ai/http://https://www.v2ex.com/api/topics/hot.json"],
            )
        )
    if _channel_enabled(doctor_text, "RSS/Atom"):
        queries.append(
            (
                "rss_search_hint",
                ["curl.exe", "-s", f"https://r.jina.ai/http://https://www.google.com/search?q={escaped}+rss"],
            )
        )
    if _channel_enabled(doctor_text, "B站"):
        queries.append(
            (
                "bilibili_search_hint",
                ["curl.exe", "-s", f"https://r.jina.ai/http://https://search.bilibili.com/all?keyword={escaped}"],
            )
        )
    queries.append(("agent_reach_doctor", [AGENT_REACH_EXE, "doctor"]))
    return queries


def _evidence_lines(text: str, *, limit: int = 4) -> list[str]:
    lines = []
    for raw in text.replace("\r", "\n").split("\n"):
        line = " ".join(raw.strip().split())
        if not line:
            continue
        lines.append(line[:240])
        if len(lines) >= limit:
            break
    return lines


def _confidence(source_count: int, ok_count: int) -> str:
    if source_count <= 0 or ok_count <= 0:
        return "low"
    ratio = ok_count / source_count
    if ratio >= 0.75:
        return "high"
    if ratio >= 0.4:
        return "medium"
    return "low"


def _collect_keyword_signals(
    results: list[dict[str, Any]],
    *,
    keywords: list[str],
    max_items: int = 5,
) -> list[dict[str, str]]:
    signals = []
    lowered_keywords = [keyword.lower() for keyword in keywords]
    for item in results:
        if item.get("status") != "ok":
            continue
        source = str(item.get("source") or "")
        summary = str(item.get("summary") or "")
        summary_lower = summary.lower()
        if not any(keyword in summary_lower for keyword in lowered_keywords):
            continue
        evidence = _evidence_lines(summary, limit=1)
        if not evidence:
            continue
        signals.append(
            {
                "source": source,
                "signal": evidence[0],
                "confidence": "medium",
            }
        )
        if len(signals) >= max_items:
            break
    return signals


def _competitor_clues(results: list[dict[str, Any]], *, max_items: int = 5) -> list[dict[str, str]]:
    clues = []
    for item in results:
        if item.get("status") != "ok":
            continue
        source = str(item.get("source") or "")
        if source not in {"github", "web", "bilibili_search_hint"}:
            continue
        for line in _evidence_lines(str(item.get("summary") or ""), limit=3):
            clues.append(
                {
                    "source": source,
                    "competitor_or_reference": line,
                    "why_it_matters": "Use this to avoid a generic clone and identify gaps for a smaller MVP.",
                }
            )
            if len(clues) >= max_items:
                return clues
    return clues


def _recommended_angles(
    topic: str,
    *,
    source_names: list[str],
    pain_points: list[dict[str, str]],
    trend_signals: list[dict[str, str]],
    competitors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    evidence_sources = source_names[:4]
    angles: list[dict[str, Any]] = [
        {
            "angle": f"Offline-first {topic.strip()} utility",
            "rationale": "Fits a small Android MVP and avoids backend, account, and real-time collaboration risk.",
            "mvp_fit": "single or two-screen app; SharedPreferences storage; no login; no payments",
            "evidence_sources": evidence_sources,
            "risk": "Validate Play competitor reviews before committing to store positioning.",
        }
    ]
    if pain_points:
        angles.append(
            {
                "angle": "No-ads, low-friction alternative",
                "rationale": "Detected pain signals suggest a simpler paid/ad-free or offline positioning may be easier to explain.",
                "mvp_fit": "local data, clear default workflow, minimal settings",
                "evidence_sources": sorted({item["source"] for item in pain_points}),
                "risk": "Anchor the first version on one painful workflow instead of broad feature coverage.",
            }
        )
    if trend_signals or competitors:
        angles.append(
            {
                "angle": "Narrow niche variant instead of broad category clone",
                "rationale": "Trend and competitor clues indicate the category may be crowded; narrow by audience, region, or scenario.",
                "mvp_fit": "use product_focus fields to constrain copy, defaults, and feature names",
                "evidence_sources": sorted(
                    {item.get("source", "") for item in [*trend_signals, *competitors] if item.get("source")}
                )[:4],
                "risk": "Keep the requirement contract small enough for Agent B to implement reliably.",
            }
        )
    return angles[:3]


def _analyze_results(topic: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    ok_sources = [str(item.get("source")) for item in results if item.get("status") == "ok"]
    source_count = len(results)
    ok_count = len(ok_sources)
    pain_points = _collect_keyword_signals(
        results,
        keywords=[
            "ad",
            "ads",
            "subscription",
            "paywall",
            "complex",
            "crash",
            "privacy",
            "offline",
            "login",
            "slow",
            "广告",
            "订阅",
            "付费",
            "复杂",
            "崩溃",
            "隐私",
            "离线",
            "登录",
            "卡顿",
            "差评",
            "痛点",
        ],
    )
    trend_signals = _collect_keyword_signals(
        results,
        keywords=[
            "popular",
            "hot",
            "trending",
            "stars",
            "updated",
            "release",
            "2025",
            "2026",
            "ai",
            "remote",
            "habit",
            "focus",
            "timer",
            "热门",
            "趋势",
            "搜索",
            "更新",
        ],
    )
    competitors = _competitor_clues(results)
    return {
        "method": "Heuristic compression of multi-source command output. Use sources as evidence, not as final requirement fields.",
        "coverage": {
            "source_count": source_count,
            "ok_count": ok_count,
            "confidence": _confidence(source_count, ok_count),
            "ok_sources": ok_sources,
        },
        "pain_points": pain_points,
        "trend_signals": trend_signals,
        "competitor_clues": competitors,
        "recommended_angles": _recommended_angles(
            topic,
            source_names=ok_sources,
            pain_points=pain_points,
            trend_signals=trend_signals,
            competitors=competitors,
        ),
        "craftsman_contract_guardrail": "Keep this analysis inside Hunter discovery. Agent B should still receive only the validated AppOpportunityBlueprint requirement payload.",
    }


@tool
def agent_reach_search(
    topic: str,
    max_sources: int = 5,
) -> str:
    """Search multiple installed Agent Reach-compatible sources before choosing a product direction."""
    doctor_text = _doctor_text()
    queries = _build_queries(topic, doctor_text)
    max_sources = max(1, min(int(max_sources), len(queries)))
    results = [_safe_call(source, command) for source, command in queries[:max_sources]]
    analysis = _analyze_results(topic.strip(), results)
    payload = {
        "topic": topic.strip(),
        "source_count": len(results),
        "ok_count": sum(1 for item in results if item["status"] == "ok"),
        "doctor_snapshot": doctor_text[:1200],
        "analysis": analysis,
        "sources": results,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

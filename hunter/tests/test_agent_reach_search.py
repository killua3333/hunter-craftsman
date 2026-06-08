import json
from unittest.mock import patch

from hunter.tools.agent_reach_search import agent_reach_search


def test_agent_reach_search_collects_multiple_sources():
    responses = {
        "gh": "repo-a stars 1200\nrepo-b updated 2026",
        "curl_v2ex": '[{"title":"remote work tools hot topic"}]',
        "curl_web": "users complain about ads, subscription, and complex setup",
    }

    def fake_run(command, *, timeout=20):
        joined = " ".join(command)
        if "gh search repos" in joined:
            return responses["gh"]
        if "v2ex.com/api/topics/hot.json" in joined:
            return responses["curl_v2ex"]
        if "google.com/search" in joined:
            return responses["curl_web"]
        return "doctor ok"

    doctor = "✅ V2EX 节点、主题与回复\n✅ RSS/Atom 订阅源\n✅ B站视频、字幕和搜索"

    with (
        patch("hunter.tools.agent_reach_search._run_command", side_effect=fake_run),
        patch("hunter.tools.agent_reach_search._doctor_text", return_value=doctor),
    ):
        out = agent_reach_search.invoke({"topic": "pomodoro timer", "max_sources": 5})

    data = json.loads(out)
    assert data["topic"] == "pomodoro timer"
    assert data["source_count"] == 5
    assert data["ok_count"] == 5
    assert "V2EX" in data["doctor_snapshot"]
    assert data["sources"][0]["source"] == "github"
    assert any(item["source"] == "rss_search_hint" for item in data["sources"])
    assert any(item["source"] == "bilibili_search_hint" for item in data["sources"])
    assert data["analysis"]["coverage"]["confidence"] == "high"
    assert data["analysis"]["pain_points"]
    assert data["analysis"]["trend_signals"]
    assert data["analysis"]["competitor_clues"]
    assert data["analysis"]["recommended_angles"]
    assert "AppOpportunityBlueprint" in data["analysis"]["craftsman_contract_guardrail"]


def test_agent_reach_search_handles_failures():
    def fake_run(command, *, timeout=20):
        joined = " ".join(command)
        if "gh search repos" in joined:
            raise RuntimeError("gh failed")
        return "ok"

    with (
        patch("hunter.tools.agent_reach_search._run_command", side_effect=fake_run),
        patch("hunter.tools.agent_reach_search._doctor_text", return_value=""),
    ):
        out = agent_reach_search.invoke({"topic": "habit tracker", "max_sources": 2})

    data = json.loads(out)
    assert data["source_count"] == 2
    assert data["ok_count"] == 1
    assert data["sources"][0]["status"] == "error"
    assert data["analysis"]["coverage"]["confidence"] == "medium"

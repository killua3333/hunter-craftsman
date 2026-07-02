from __future__ import annotations

import json

from hunter.discovery import play_monitor


class _FakeTool:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def invoke(self, payload):
        self.calls.append(payload)
        if len(self.payloads) == 1:
            return json.dumps(self.payloads[0])
        return json.dumps(self.payloads.pop(0))


def test_play_discovery_run_records_monitorable_evidence(monkeypatch):
    competitive = _FakeTool(
        [
            {
                "competitive_matrix": [
                    {
                        "appId": "com.example.timer",
                        "title": "Timer Pro",
                        "score": 3.4,
                        "installs": "100,000+",
                        "stale": True,
                        "ripe": True,
                    },
                    {
                        "appId": "com.example.simple",
                        "title": "Simple Timer",
                        "score": 4.1,
                        "installs": "10,000+",
                        "stale": False,
                        "ripe": False,
                    },
                ]
            }
        ]
    )
    reviews = _FakeTool(
        [
            {
                "app_id": "com.example.timer",
                "total_low_score_reviews": 12,
                "pain_points": [
                    {"theme": "ads", "frequency_pct": 50, "review_count": 6},
                    {"theme": "too complex", "frequency_pct": 25, "review_count": 3},
                ],
            },
            {
                "app_id": "com.example.simple",
                "total_low_score_reviews": 2,
                "pain_points": [{"theme": "missing offline mode", "frequency_pct": 50, "review_count": 1}],
            },
        ]
    )
    monkeypatch.setattr(play_monitor, "play_competitive_analysis", competitive)
    monkeypatch.setattr(play_monitor, "play_analyze_reviews", reviews)

    run = play_monitor.build_play_discovery_run(seed_queries=["simple timer"], competitors_per_query=2)

    assert run["discovery_run_id"].startswith("disc-")
    assert run["seed_queries"] == ["simple timer"]
    assert len(run["searched_apps"]) == 2
    assert run["low_score_reviews"]
    assert run["pain_point_clusters"][0]["theme"] == "ads"
    assert run["candidate_opportunities"][0]["source_apps"]
    assert run["candidate_opportunities"][0]["review_pain_summary"]
    assert run["final_selected_opportunity"]["niche"] == "simple timer"
    assert run["data_quality"] == "measured"


def test_discovery_prompt_forces_candidate_pool_selection():
    prompt = play_monitor.discovery_run_to_prompt(
        {
            "discovery_run_id": "disc-test",
            "seed_queries": ["timer"],
            "pain_point_clusters": [],
            "candidate_opportunities": [{"name": "Timer MVP"}],
            "rejected_candidates": [],
            "final_selected_opportunity": {"name": "Timer MVP"},
            "data_quality": "mixed",
        }
    )

    assert "candidate_opportunities" in prompt
    assert "disc-test" in prompt
    assert "source_apps" in prompt

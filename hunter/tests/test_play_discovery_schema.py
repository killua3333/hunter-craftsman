from __future__ import annotations

from hunter.integrations.craftsman import build_requirement_from_blueprint
from tests.conftest import sample_blueprint


def test_requirement_preserves_play_discovery_fields():
    bp = sample_blueprint(
        data_quality="measured",
        evidence=[{"query": "timer", "source": "play://com.example.timer", "snippet": "ads"}],
        evidence_score=88,
        source_apps=[{"appId": "com.example.timer", "title": "Timer Pro", "score": 3.4}],
        review_pain_summary=[{"theme": "ads", "review_count": 6}],
        discovery_run_id="disc-test",
    )

    requirement = build_requirement_from_blueprint(bp, opportunity_id="opp-play")
    meta = requirement["opportunity_meta"]

    assert meta["evidence_score"] == 88
    assert meta["source_apps"][0]["appId"] == "com.example.timer"
    assert meta["review_pain_summary"][0]["theme"] == "ads"
    assert meta["discovery_run_id"] == "disc-test"

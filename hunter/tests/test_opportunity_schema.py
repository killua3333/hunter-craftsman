import json

import pytest

from hunter.schemas import AppOpportunityBlueprint, blueprint_for_agent_b, parse_blueprint
from tests.conftest import sample_blueprint


def test_accepted_blueprint():
    bp = sample_blueprint()
    agent_b = blueprint_for_agent_b(bp)
    assert agent_b["platform"]["target"] == "android"
    assert agent_b["app"]["name"] == "离线番茄钟"
    assert agent_b["core_logic"]["persistence"] == "UserDefaults"
    assert "accent_color" not in agent_b["branding"]


def test_rejected_blueprint():
    bp = AppOpportunityBlueprint(
        accepted=False,
        rejection_reason="需要后端用户体系",
    )
    assert bp.accepted is False
    with pytest.raises(ValueError, match="后端"):
        blueprint_for_agent_b(bp)


def test_accepted_missing_requirement_raises():
    with pytest.raises(ValueError, match="requirement"):
        AppOpportunityBlueprint(
            accepted=True,
            app_name="番茄钟",
            core_logic="本地计时。",
            ui_layout="中央按钮。",
            keywords=["专注"],
            data_quality="assumption",
            evidence=[
                {
                    "query": "q",
                    "source": "assumption://x",
                    "snippet": "s",
                }
            ],
        )


def test_measured_requires_evidence():
    with pytest.raises(ValueError, match="evidence"):
        sample_blueprint(data_quality="measured", evidence=[])


def test_roundtrip_json():
    bp = sample_blueprint()
    text = json.dumps(bp.model_dump(), ensure_ascii=False)
    restored = parse_blueprint(text)
    assert restored.app_name == "离线番茄钟"

import json

import pytest

from hunter.integrations.craftsman import build_requirement_from_blueprint
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


def test_opportunity_metadata_fields_parse():
    bp = sample_blueprint(
        niche="离线计时器",
        target_users="需要无广告专注工具的学生",
        pain_points=["广告太多", "界面复杂", "离线不可用"],
        competitor_gap="竞品臃肿且广告多",
        opportunity_score=62,
        build_fit_score=92,
        decision_reason="纯前端本地 MVP，适合快速实现",
        rejected_candidates=[{"name": "云同步清单", "reason": "需要账号体系", "build_fit_score": 35}],
    )
    assert bp.niche == "离线计时器"
    assert bp.build_fit_score == 92
    assert bp.rejected_candidates[0].reason == "需要账号体系"


def test_assumption_opportunity_score_capped():
    with pytest.raises(ValueError, match="opportunity_score"):
        sample_blueprint(opportunity_score=80)


def test_requirement_preserves_opportunity_meta():
    bp = sample_blueprint(
        niche="离线计时器",
        target_users="需要简单专注工具的学生",
        pain_points=["广告太多", "界面复杂", "离线不可用"],
        competitor_gap="竞品功能臃肿",
        opportunity_score=62,
        build_fit_score=92,
        decision_reason="纯本地工具，适合快速生成 MVP",
        rejected_candidates=[{"name": "云同步清单", "reason": "需要账号体系", "build_fit_score": 35}],
    )
    requirement = build_requirement_from_blueprint(bp, opportunity_id="opp-meta")
    meta = requirement["opportunity_meta"]
    assert meta["niche"] == "离线计时器"
    assert meta["build_fit_score"] == 92
    assert meta["pain_points"] == ["广告太多", "界面复杂", "离线不可用"]
    assert meta["rejected_candidates"][0]["name"] == "云同步清单"

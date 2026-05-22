import pytest

from hunter.integrations import build_requirement_from_blueprint
from tests.conftest import sample_blueprint


def test_build_requirement_from_blueprint():
    blueprint = sample_blueprint()
    req = build_requirement_from_blueprint(blueprint, opportunity_id="focus-001")

    assert req["opportunity_id"] == "focus-001"
    assert req["schema_version"] == "1.0"
    assert req["app"]["name"] == "离线番茄钟"
    assert req["core_logic"]["persistence"] == "UserDefaults"
    assert req["ui_layout"]["navigation"] == "stack"
    assert req["data_quality"] == "assumption"
    assert len(req["evidence"]) == 1


def test_rejected_blueprint_cannot_build_requirement():
    from hunter.schemas import AppOpportunityBlueprint

    blueprint = AppOpportunityBlueprint(
        accepted=False,
        rejection_reason="需要后端账号系统",
    )
    with pytest.raises(ValueError, match="rejected"):
        build_requirement_from_blueprint(blueprint)

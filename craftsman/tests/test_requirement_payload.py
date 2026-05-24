from craftsman.models import RequirementPayload
from craftsman.orchestrator.pipeline import analyze_requirement


def test_payload_preserves_data_quality_and_evidence():
    raw = {
        "schema_version": "1.0",
        "opportunity_id": "demo-app-05220921",
        "revision": 3,
        "platform": {"target": "android"},
        "data_quality": "measured",
        "evidence": [
            {
                "query": "番茄钟",
                "source": "https://example.com/a",
                "snippet": "广告太多",
            }
        ],
        "app": {
            "name": "极简番茄钟",
            "bundle_id": "com.hunter.minipomodoro",
            "application_id": "com.hunter.minipomodoro",
            "min_android_sdk": "24",
        },
        "features": [
            {"id": "timer", "type": "list", "title": "计时", "items": ["25分钟"]}
        ],
        "core_logic": {"persistence": "SharedPreferences", "description": "计时逻辑"},
        "ui_layout": {"navigation": "single", "screens": ["主屏"]},
        "branding": {"primary_color": "#E74C3C", "icon_text": "番"},
        "store": {
            "subtitle": "专注",
            "description": "离线番茄钟",
            "keywords": ["番茄钟"],
            "privacy_url": "https://example.com/privacy",
        },
        "budget": {"max_features": 8, "max_hours": 2.0},
    }
    payload = RequirementPayload.model_validate(raw).as_dict()
    assert payload["platform"]["target"] == "android"
    assert payload["data_quality"] == "measured"
    assert len(payload["evidence"]) == 1

    fb = analyze_requirement(raw)
    assert fb.blueprint.accepted is True
    assert fb.agent_b_status.value == "accepted"

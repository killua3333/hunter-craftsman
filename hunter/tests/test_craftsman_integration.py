from hunter.integrations.craftsman import build_requirement_from_blueprint
from hunter.schemas.opportunity import AppOpportunityBlueprint


def test_build_requirement_includes_agent_a_context():
    blueprint = AppOpportunityBlueprint.model_validate(
        {
            "accepted": True,
            "app_name": "Pomodoro",
            "core_logic": "Offline timer with local stats",
            "ui_layout": "Single main timer screen",
            "keywords": ["timer"],
            "data_quality": "assumption",
            "evidence": [
                {
                    "query": "offline timer",
                    "source": "assumption://manual",
                    "snippet": "Assume users want offline focus timing.",
                }
            ],
            "requirement": {
                "platform": {"target": "android"},
                "app": {
                    "name": "Pomodoro",
                    "bundle_id": "com.hunter.pomodoro",
                    "application_id": "com.hunter.pomodoro",
                    "version": "1.0.0",
                    "build": "1",
                    "min_android_sdk": "24",
                },
                "features": [
                    {
                        "id": "timer",
                        "type": "list",
                        "title": "Timer",
                        "items": ["Start countdown", "Pause and resume"],
                    }
                ],
                "core_logic": {
                    "persistence": "SharedPreferences",
                    "description": "Store timer presets and session count.",
                },
                "ui_layout": {
                    "navigation": "single",
                    "screens": ["Main timer screen with preset chips and stats"],
                },
                "branding": {"primary_color": "#007AFF", "icon_text": "P"},
                "store": {
                    "subtitle": "Focus timer",
                    "description": "An offline focus timer",
                    "keywords": ["timer"],
                    "privacy_url": "https://example.com/privacy",
                },
                "budget": {"max_features": 4, "max_hours": 2.0},
            },
        }
    )
    blueprint.summary = "Build the smallest offline focus timer first."
    blueprint.estimated_complexity = "low"
    blueprint.open_questions = ["Should completed sessions be editable?"]
    blueprint.reasons = ["Keep the implementation fully offline."]

    req = build_requirement_from_blueprint(blueprint, opportunity_id="pomodoro-1", revision=2)

    assert req["agent_a_context"]["summary"] == "Build the smallest offline focus timer first."
    assert req["agent_a_context"]["estimated_complexity"] == "low"
    assert req["agent_a_context"]["open_questions"] == ["Should completed sessions be editable?"]
    assert req["agent_a_context"]["reasons"] == ["Keep the implementation fully offline."]

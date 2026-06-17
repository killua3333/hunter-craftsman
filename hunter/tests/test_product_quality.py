from hunter.schemas import parse_blueprint


def test_parse_blueprint_preserves_product_quality():
    raw = {
        "accepted": True,
        "app_name": "Focus Flow",
        "core_logic": "Local focus timer with session history",
        "ui_layout": "Single screen with timer and stats",
        "keywords": ["focus", "timer"],
        "data_quality": "assumption",
        "evidence": [
            {
                "query": "focus timer users",
                "source": "assumption://play",
                "snippet": "Users want fewer generic screens.",
            }
        ],
        "requirement": {
            "platform": {"target": "android"},
            "app": {"name": "Focus Flow", "bundle_id": "com.hunter.focusflow"},
            "features": [
                {"id": "timer", "type": "list", "title": "Timer", "items": ["Start", "Pause", "Complete session"]}
            ],
            "core_logic": {"persistence": "SharedPreferences", "description": "Store session history locally."},
            "ui_layout": {"navigation": "single", "screens": ["Timer and daily stats"]},
            "branding": {"primary_color": "#4A90D9", "icon_text": "F"},
            "store": {
                "subtitle": "Focus timer",
                "description": "Offline focus sessions",
                "keywords": ["focus", "timer"],
                "privacy_url": "https://example.com/privacy",
            },
            "budget": {"max_features": 4, "max_hours": 2.0},
            "product_quality": {
                "target": "verified",
                "interaction_depth": "polished",
                "risks": ["android_smoke_not_executed"],
            },
        },
    }
    bp = parse_blueprint(raw)
    assert bp.requirement is not None
    assert bp.requirement.product_quality.target == "verified"
    assert bp.requirement.product_quality.interaction_depth == "polished"
    assert bp.requirement.product_quality.risks == ["android_smoke_not_executed"]


def test_product_quality_self_check_flags_generic_requirement():
    raw = {
        "accepted": True,
        "app_name": "Quick Tool",
        "core_logic": "tool",
        "ui_layout": "主屏",
        "keywords": ["tool"],
        "data_quality": "assumption",
        "evidence": [
            {
                "query": "tool app",
                "source": "assumption://play",
                "snippet": "Users dislike generic tools.",
            }
        ],
        "requirement": {
            "platform": {"target": "android"},
            "app": {"name": "Quick Tool", "bundle_id": "com.hunter.quicktool"},
            "features": [{"id": "main", "type": "list", "title": "Home", "items": ["Start"]}],
            "core_logic": {"persistence": "SharedPreferences", "description": "tool"},
            "ui_layout": {"navigation": "single", "screens": ["Home"]},
            "branding": {"primary_color": "#4A90D9", "icon_text": "Q"},
            "store": {
                "subtitle": "tool",
                "description": "tool",
                "keywords": ["tool"],
                "privacy_url": "https://example.com/privacy",
            },
            "budget": {"max_features": 2, "max_hours": 1.0},
        },
    }
    bp = parse_blueprint(raw)
    assert bp.requirement is not None
    assert bp.requirement.product_quality.interaction_depth == "generic"
    assert "generic_feature_titles" in bp.requirement.product_quality.risks
    assert "generic_screen_definition" in bp.requirement.product_quality.risks


def test_product_quality_self_check_keeps_specific_requirement_task_focused():
    raw = {
        "accepted": True,
        "app_name": "Focus Flow",
        "core_logic": "Local focus timer with presets and session history",
        "ui_layout": "Timer with presets and history",
        "keywords": ["focus", "timer"],
        "data_quality": "assumption",
        "evidence": [
            {
                "query": "focus timer users",
                "source": "assumption://play",
                "snippet": "Users want session history and presets.",
            }
        ],
        "requirement": {
            "platform": {"target": "android"},
            "app": {"name": "Focus Flow", "bundle_id": "com.hunter.focusflow"},
            "features": [
                {"id": "timer", "type": "list", "title": "Focus Timer", "items": ["Start 25m session", "Pause current session", "Finish and save session"]},
                {"id": "history", "type": "detail", "title": "Session History", "items": ["View completed sessions", "Tap to inspect daily totals"]},
            ],
            "core_logic": {"persistence": "SharedPreferences", "description": "Store presets, running timer state, and session history locally."},
            "ui_layout": {"navigation": "single", "screens": ["Timer controls and daily progress summary"]},
            "branding": {"primary_color": "#4A90D9", "icon_text": "F"},
            "store": {
                "subtitle": "Focus timer",
                "description": "Offline focus sessions",
                "keywords": ["focus", "timer"],
                "privacy_url": "https://example.com/privacy",
            },
            "budget": {"max_features": 4, "max_hours": 2.0},
        },
    }
    bp = parse_blueprint(raw)
    assert bp.requirement is not None
    assert bp.requirement.product_quality.interaction_depth == "task_focused"
    assert "generic_feature_titles" not in bp.requirement.product_quality.risks

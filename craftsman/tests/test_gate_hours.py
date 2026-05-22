from craftsman.gate import run_gate


def _pomodoro_like_req() -> dict:
    return {
        "app": {"name": "极简番茄钟", "bundle_id": "com.hunter.pomodoro"},
        "features": [
            {"id": "timer", "type": "list", "title": "计时", "items": ["a", "b", "c"]},
            {"id": "stats", "type": "detail", "title": "统计", "items": ["x"]},
            {"id": "settings", "type": "form", "title": "设置", "items": ["y"]},
        ],
        "core_logic": {"persistence": "UserDefaults", "description": "计时与统计"},
        "ui_layout": {"navigation": "single", "screens": ["主屏"]},
        "branding": {"primary_color": "#E74C3C", "icon_text": "番"},
        "store": {
            "subtitle": "专注",
            "description": "极简番茄钟",
            "keywords": ["番茄钟"],
            "privacy_url": "https://example.com/privacy",
        },
        "budget": {"max_features": 8, "max_hours": 2.0},
        "capabilities": [
            "本地通知",
            "触觉反馈",
            "系统声音",
            "Info.plist 说明",
        ],
        "data_quality": "measured",
        "evidence": [
            {
                "query": "番茄钟",
                "source": "https://example.com/a",
                "snippet": "广告太多",
            }
        ],
    }


def test_three_features_with_capabilities_passes_budget():
    result = run_gate(_pomodoro_like_req(), [])
    assert result.accepted, result.reasons
    assert not any("超过预算" in r for r in result.reasons)

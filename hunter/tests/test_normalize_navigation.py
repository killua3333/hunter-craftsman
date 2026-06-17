"""ui_layout.navigation 误写 tab_root 时应自动修正为 tab。"""

from hunter.schemas import parse_blueprint


def test_navigation_tab_root_maps_to_tab():
    raw = {
        "accepted": True,
        "app_name": "极简番茄钟",
        "core_logic": "本地番茄钟计时",
        "ui_layout": "单屏计时器+底部统计页",
        "keywords": ["番茄钟", "专注"],
        "data_quality": "assumption",
        "evidence": [
            {
                "query": "Pomodoro ads",
                "source": "assumption://play",
                "snippet": "广告过多",
            }
        ],
        "requirement": {
            "platform": {"target": "android"},
            "app": {"name": "极简番茄钟", "bundle_id": "com.hunter.pomodoro"},
            "features": [
                {
                    "id": "timer",
                    "type": "form",
                    "title": "番茄计时器",
                    "items": ["25分钟倒计时"],
                }
            ],
            "core_logic": {
                "persistence": "SharedPreferences",
                "description": "存番茄计数",
            },
            "ui_layout": {
                "navigation": "tab_root",
                "screens": ["计时器", "统计", "设置"],
            },
            "branding": {"primary_color": "#E74C3C", "icon_text": "番"},
            "store": {
                "subtitle": "极简",
                "description": "无广告",
                "keywords": ["番茄钟"],
                "privacy_url": "https://example.com/privacy",
            },
            "budget": {"max_features": 8, "max_hours": 2},
        },
    }
    bp = parse_blueprint(raw)
    assert bp.requirement is not None
    assert bp.requirement.ui_layout.navigation == "tab"
    assert len(bp.requirement.ui_layout.screens) == 3
    assert bp.requirement.product_quality.target == "verified"
    assert bp.requirement.product_quality.risks == []

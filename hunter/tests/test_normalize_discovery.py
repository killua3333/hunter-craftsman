"""Autopilot 发现模式常见非标准 JSON 变体。"""

from hunter.schemas import parse_blueprint


def _countdown_discovery_raw() -> dict:
    """模拟用户遇到的 app_idea + 嵌套 requirement 形状（完整版）。"""
    return {
        "accepted": True,
        "app_idea": {
            "title": "极简倒数日 · 无广告倒计时 Widget",
            "tagline": "最干净的倒数日工具",
        },
        "opportunity": {
            "pain_points": ["广告过多", "备注框太小"],
            "evidence": [
                "Countdown Widget 差评：打开3分钟跳了5个广告",
                "用户渴望无广告替代品",
            ],
        },
        "requirement": {
            "platform": {"target": "android", "min_sdk": 26},
            "core_logic": {
                "main_function": "创建倒计时并显示剩余天数",
                "persistence": "SharedPreferences",
                "key_actions": ["创建事件", "列表排序", "Widget 显示"],
            },
            "features": [
                {
                    "id": "f1",
                    "title": "创建倒计时事件",
                    "type": "core",
                    "items": ["输入标题", "选择日期", "保存"],
                },
                {
                    "id": "f2",
                    "title": "倒计时列表主页",
                    "type": "core",
                    "items": ["卡片列表", "显示剩余天数"],
                },
            ],
        },
    }


def test_normalize_discovery_app_idea_variant():
    bp = parse_blueprint(_countdown_discovery_raw())
    assert bp.accepted is True
    assert "倒数日" in bp.app_name
    assert bp.data_quality in ("mixed", "assumption", "measured")
    assert len(bp.evidence) >= 1
    assert bp.requirement is not None
    assert bp.requirement.app.name
    assert bp.requirement.app.bundle_id.startswith("com.hunter.")
    assert bp.requirement.core_logic.persistence == "SharedPreferences"
    assert bp.requirement.core_logic.description
    assert len(bp.requirement.features) <= 6
    assert bp.requirement.features[0].type == "list"
    assert bp.requirement.store.privacy_url

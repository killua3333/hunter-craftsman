"""Agent A 输出规范化：保证 chat /make 可解析。"""

import json

from hunter.schemas import extract_blueprint_from_text, normalize_blueprint_dict, parse_blueprint


def _pomodoro_like_raw() -> dict:
    """模拟模型常输出的非标准 features / store.keywords。"""
    return {
        "accepted": True,
        "app_name": "极简番茄钟",
        "core_logic": "本地番茄钟",
        "ui_layout": "单屏",
        "keywords": ["番茄钟", "专注"],
        "data_quality": "measured",
        "evidence": [
            {
                "query": "番茄钟 app",
                "source": "https://example.com",
                "snippet": "用户需要无广告离线计时",
            }
        ],
        "requirement": {
            "app": {"name": "极简番茄钟", "bundle_id": "com.hunter.minimalpomodoro"},
            "features": [
                {
                    "name": "番茄计时器",
                    "type": "list",
                    "description": "核心计时功能",
                    "items": [
                        {
                            "name": "倒计时显示",
                            "type": "text",
                            "description": "MM:SS 大字体",
                        },
                        {"name": "开始/暂停", "description": "点击切换"},
                    ],
                }
            ],
            "core_logic": {
                "persistence": "UserDefaults",
                "description": "键 todayCount 存 Int",
            },
            "ui_layout": {
                "navigation": "single",
                "screens": ["主屏 VStack 倒计时与按钮"],
            },
            "branding": {"primary_color": "#E74C3C", "icon_text": "番"},
            "store": {
                "subtitle": "极简番茄钟",
                "description": "无广告离线",
                "keywords": "番茄钟,专注,计时器,离线",
                "privacy_url": "https://example.com/privacy",
            },
            "budget": {"max_features": 3, "max_hours": 2},
        },
    }


def test_normalize_pomodoro_like_dict():
    bp = parse_blueprint(_pomodoro_like_raw())
    assert bp.accepted is True
    assert bp.app_name == "极简番茄钟"
    feat = bp.requirement.features[0]
    assert feat.id == "番茄计时器" or feat.title == "番茄计时器"
    assert all(isinstance(x, str) for x in feat.items)
    assert len(feat.items) >= 2
    assert bp.requirement.store.keywords == ["番茄钟", "专注", "计时器", "离线"]


def test_extract_fence_with_normalized_shape():
    raw = _pomodoro_like_raw()
    text = f"```json\n{json.dumps(raw, ensure_ascii=False)}\n```"
    bp = extract_blueprint_from_text(text)
    assert bp.accepted is True
    assert bp.requirement.features[0].title

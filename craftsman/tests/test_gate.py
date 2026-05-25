from craftsman.gate import run_gate


def _strict_gate(monkeypatch):
    from craftsman.config import settings

    monkeypatch.setattr(settings, "gate_mode", "strict")
    monkeypatch.setattr(settings, "gate_auto_accept", False)


def test_gate_rejects_missing_persistence(monkeypatch):
    _strict_gate(monkeypatch)
    req = {
        "app": {"name": "Test"},
        "features": [{"id": "a", "type": "list", "title": "T"}],
        "ui_layout": {"navigation": "stack"},
        "store": {"privacy_url": "https://example.com/p"},
        "branding": {"primary_color": "#112233"},
    }
    result = run_gate(req, [])
    assert not result.accepted
    assert any("存储" in r for r in result.reasons)


def test_gate_accepts_complete():
    req = {
        "app": {"name": "Test", "bundle_id": "com.test.app"},
        "features": [{"id": "a", "type": "list", "title": "T", "items": ["x"]}],
        "core_logic": {"persistence": "none", "description": "本地计时"},
        "ui_layout": {"navigation": "stack"},
        "store": {
            "privacy_url": "https://example.com/p",
            "subtitle": "s",
            "description": "d",
            "keywords": ["a"],
        },
        "branding": {"primary_color": "#112233", "icon_text": "T"},
        "budget": {"max_features": 8, "max_hours": 2},
        "data_quality": "assumption",
        "evidence": [
            {
                "query": "q",
                "source": "assumption://合理推断",
                "snippet": "学生需要极简番茄钟",
            }
        ],
    }
    result = run_gate(req, [])
    assert result.accepted
    assert result.reasons == []

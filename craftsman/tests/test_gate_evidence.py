from craftsman.gate import run_gate


def _minimal_req(**extra):
    base = {
        "app": {"name": "Test", "bundle_id": "com.test.app"},
        "features": [{"id": "home", "type": "list", "title": "Home"}],
        "core_logic": {"persistence": "UserDefaults", "description": "x"},
        "ui_layout": {"navigation": "stack"},
        "branding": {"primary_color": "#007AFF", "icon_text": "T"},
        "store": {
            "subtitle": "s",
            "description": "d",
            "keywords": ["a"],
            "privacy_url": "https://example.com/privacy",
        },
        "budget": {"max_features": 8, "max_hours": 2},
    }
    base.update(extra)
    return base


def test_gate_rejects_missing_data_quality():
    result = run_gate(_minimal_req(), [])
    assert any("data_quality" in r for r in result.reasons)


def test_gate_rejects_measured_with_only_assumption():
    result = run_gate(
        _minimal_req(
            data_quality="measured",
            evidence=[
                {
                    "query": "q",
                    "source": "assumption://guess",
                    "snippet": "s",
                }
            ],
        ),
        [],
    )
    assert any("measured" in r for r in result.reasons)


def test_gate_accepts_assumption_evidence():
    result = run_gate(
        _minimal_req(
            data_quality="assumption",
            evidence=[
                {
                    "query": "q",
                    "source": "assumption://合理推断",
                    "snippet": "s",
                }
            ],
        ),
        [],
    )
    assert not any("data_quality" in r for r in result.reasons)
    assert not any("evidence" in r and "缺少" in r for r in result.reasons)

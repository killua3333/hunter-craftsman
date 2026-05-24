from craftsman.gate import run_gate
from craftsman.requirement_normalize import soft_fill_requirement


def test_soft_gate_accepts_minimal_req(monkeypatch):
    from craftsman.config import settings

    monkeypatch.setattr(settings, "gate_mode", "soft")
    monkeypatch.setattr(settings, "gate_auto_accept", True)

    req = {
        "app": {"name": "Quick Tool"},
        "features": [{"id": "main", "type": "list", "title": "Home"}],
    }
    result = run_gate(req, [])
    assert result.accepted
    assert result.reasons == []


def test_soft_fill_adds_defaults():
    filled = soft_fill_requirement({"app": {"name": "Demo"}})
    assert filled["app"]["bundle_id"]
    assert filled["core_logic"]["persistence"]
    assert filled["store"]["privacy_url"]
    assert filled["data_quality"] == "assumption"
    assert filled["evidence"]

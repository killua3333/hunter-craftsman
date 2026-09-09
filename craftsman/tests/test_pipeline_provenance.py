from craftsman.config import settings
from craftsman.orchestrator.pipeline import _coding_provenance


def test_deepseek_harness_provenance_uses_active_flash_model(monkeypatch):
    monkeypatch.setattr(settings, "coding_provider", "deepseek_harness")
    monkeypatch.setattr(settings, "deepseek_harness_model", "deepseek-v4-flash")
    monkeypatch.setattr(settings, "deepseek_pro_model", "deepseek-v4-pro")

    assert _coding_provenance() == {
        "codegen_provider": "deepseek_harness",
        "codegen_model": "deepseek-v4-flash",
    }


def test_json_codegen_provenance_uses_configured_model(monkeypatch):
    monkeypatch.setattr(settings, "coding_provider", "deepseek_json")
    monkeypatch.setattr(settings, "deepseek_pro_model", "deepseek-chat")

    assert _coding_provenance() == {
        "codegen_provider": "deepseek_json",
        "codegen_model": "deepseek-chat",
    }

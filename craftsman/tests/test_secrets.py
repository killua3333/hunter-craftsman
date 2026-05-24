from pathlib import Path

from craftsman.config import settings
from craftsman.secrets import resolve_secret_value


def test_secret_provider_env_prefers_env_value(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "secret_provider", "env")
    monkeypatch.setattr(settings, "secret_store_dir", tmp_path / "secrets")
    value = resolve_secret_value("API_TOKEN", "env-token")
    assert value == "env-token"


def test_secret_provider_file_reads_store(tmp_path, monkeypatch):
    store = tmp_path / "secrets"
    store.mkdir(parents=True)
    (store / "API_TOKEN").write_text("file-token\n", encoding="utf-8")
    monkeypatch.setattr(settings, "secret_provider", "file")
    monkeypatch.setattr(settings, "secret_store_dir", store)
    value = resolve_secret_value("API_TOKEN", "env-token")
    assert value == "file-token"


def test_secret_provider_fallback_reads_file_when_env_missing(tmp_path, monkeypatch):
    store = tmp_path / "secrets"
    store.mkdir(parents=True)
    (store / "openai_api_key.txt").write_text("store-openai-key", encoding="utf-8")
    monkeypatch.setattr(settings, "secret_provider", "env_file_fallback")
    monkeypatch.setattr(settings, "secret_store_dir", store)
    value = resolve_secret_value("OPENAI_API_KEY", None)
    assert value == "store-openai-key"

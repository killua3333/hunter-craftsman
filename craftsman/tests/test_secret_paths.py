from __future__ import annotations

from craftsman.config import ROOT, settings
from craftsman.secrets import resolve_secret_path


def test_relative_secret_path_resolves_from_craftsman_root(monkeypatch, tmp_path):
    secret = ROOT / "secrets" / "unit-test-secret.txt"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("ok", encoding="utf-8")
    try:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(settings, "secret_provider", "env_file_fallback")

        resolved = resolve_secret_path("UNIT_TEST_SECRET", "./secrets/unit-test-secret.txt")

        assert resolved == secret
    finally:
        secret.unlink(missing_ok=True)

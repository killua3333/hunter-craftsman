import os

from hunter.integrations.craftsman import craftsman_analyze_timeout_seconds


def test_craftsman_analyze_timeout_default():
    os.environ.pop("CRAFTSMAN_ANALYZE_TIMEOUT_SECONDS", None)
    assert craftsman_analyze_timeout_seconds() == 90.0


def test_craftsman_analyze_timeout_from_env(monkeypatch):
    monkeypatch.setenv("CRAFTSMAN_ANALYZE_TIMEOUT_SECONDS", "120")
    assert craftsman_analyze_timeout_seconds() == 120.0

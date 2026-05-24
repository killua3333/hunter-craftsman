from __future__ import annotations

import pytest

from craftsman.callback import deliver_feedback
from craftsman.config import settings
from craftsman.feedback import build_feedback
from craftsman.models import AgentBStatus


def _sample_feedback():
    return build_feedback(
        opportunity_id="op-1",
        revision=1,
        app_name="Demo",
        accepted=True,
        status=AgentBStatus.IN_PROGRESS,
    )


def test_webhook_mandatory_requires_url_and_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "callback_dir", tmp_path / "callbacks")
    monkeypatch.setattr(settings, "webhook_mandatory", True)
    monkeypatch.setattr(settings, "webhook_url", None)
    monkeypatch.setattr(settings, "webhook_secret", None)

    with pytest.raises(RuntimeError, match="WEBHOOK_URL"):
        deliver_feedback(_sample_feedback())

    monkeypatch.setattr(settings, "webhook_url", "http://example.com/hook")
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        deliver_feedback(_sample_feedback())


def test_webhook_mandatory_delivery_failure_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "callback_dir", tmp_path / "callbacks")
    monkeypatch.setattr(settings, "webhook_mandatory", True)
    monkeypatch.setattr(settings, "webhook_url", "http://example.com/hook")
    monkeypatch.setattr(settings, "webhook_secret", "secret")

    class _FailClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            raise RuntimeError("network down")

    monkeypatch.setattr("craftsman.callback.httpx.Client", lambda timeout: _FailClient())
    with pytest.raises(RuntimeError, match="mandatory webhook delivery failed"):
        deliver_feedback(_sample_feedback())


def test_webhook_mandatory_success_includes_signature(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "callback_dir", tmp_path / "callbacks")
    monkeypatch.setattr(settings, "webhook_mandatory", True)
    monkeypatch.setattr(settings, "webhook_url", "http://example.com/hook")
    monkeypatch.setattr(settings, "webhook_secret", "secret")

    captured = {}

    class _Resp:
        @staticmethod
        def raise_for_status():
            return None

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, content, headers):
            captured["url"] = url
            captured["headers"] = headers
            captured["content"] = content
            return _Resp()

    monkeypatch.setattr("craftsman.callback.httpx.Client", lambda timeout: _Client())
    deliver_feedback(_sample_feedback())
    assert captured["url"] == "http://example.com/hook"
    assert "X-Craftsman-Signature" in captured["headers"]


def test_webhook_secret_from_secret_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "callback_dir", tmp_path / "callbacks")
    monkeypatch.setattr(settings, "webhook_mandatory", True)
    monkeypatch.setattr(settings, "webhook_url", "http://example.com/hook")
    monkeypatch.setattr(settings, "webhook_secret", None)
    monkeypatch.setattr(settings, "secret_provider", "file")
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "WEBHOOK_SECRET").write_text("secret-from-file", encoding="utf-8")
    monkeypatch.setattr(settings, "secret_store_dir", secret_dir)

    captured = {}

    class _Resp:
        @staticmethod
        def raise_for_status():
            return None

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, content, headers):
            captured["headers"] = headers
            return _Resp()

    monkeypatch.setattr("craftsman.callback.httpx.Client", lambda timeout: _Client())
    deliver_feedback(_sample_feedback())
    assert "X-Craftsman-Signature" in captured["headers"]

from unittest.mock import MagicMock

import httpx
import pytest

from craftsman.publisher.privacy_policy import (
    cf_pages_asset_hash,
    deploy_to_cloudflare_pages,
    ensure_privacy_url,
    is_placeholder_privacy_url,
    render_privacy_html,
)


def test_is_placeholder_privacy_url():
    assert is_placeholder_privacy_url("https://example.com/privacy") is True
    assert is_placeholder_privacy_url("https://timer-privacy.pages.dev/") is False


def test_render_privacy_html_contains_app_name():
    html = render_privacy_html(
        {
            "app": {"name": "Timer", "bundle_id": "com.test.timer"},
            "store": {"subtitle": "Timer"},
            "core_logic": {"persistence": "localStorage"},
            "features": [{"title": "Countdown"}],
        }
    )
    assert "Timer" in html
    assert "com.test.timer" in html


def test_deploy_dry_run():
    result = deploy_to_cloudflare_pages("timer-privacy", "<html/>", dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert "pages.dev" in result["url"]


def test_cf_pages_asset_hash_deterministic():
    blake3 = pytest.importorskip("blake3")
    del blake3
    h1 = cf_pages_asset_hash(b"<html/>", "index.html")
    h2 = cf_pages_asset_hash(b"<html/>", "index.html")
    assert h1 == h2
    assert len(h1) == 32


def test_deploy_live_mock_cf(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            resp = MagicMock()
            resp.status_code = 200
            if "check-missing" in url:
                resp.json.return_value = {"success": True, "result": ["abc123"]}
            else:
                resp.json.return_value = {"success": True, "result": {}}
            return resp

        def get(self, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"success": True, "result": {"jwt": "upload-jwt"}}
            return resp

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "craftsman.publisher.privacy_policy._cf_token",
        lambda: "token",
    )
    monkeypatch.setattr(
        "craftsman.publisher.privacy_policy._cf_account",
        lambda: "account",
    )
    monkeypatch.setattr(
        "craftsman.publisher.privacy_policy.cf_pages_asset_hash",
        lambda content, filename="index.html": "abc123",
    )
    result = deploy_to_cloudflare_pages("timer-privacy", "<html/>", dry_run=False)
    assert result["ok"] is True
    assert result["url"] == "https://timer-privacy.pages.dev/"
    deploy_calls = [c for c in calls if c[0].endswith("/deployments")]
    assert deploy_calls
    assert deploy_calls[0][1]["data"]["manifest"] == '{"/index.html": "abc123"}'


def test_deploy_live_retries_on_transient_failure(monkeypatch):
    attempts = {"n": 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            attempts["n"] += 1
            resp = MagicMock()
            if attempts["n"] == 1:
                resp.status_code = 429
                resp.json.return_value = {"success": False, "errors": [{"message": "rate limited"}]}
                raise RuntimeError("rate limited")
            resp.status_code = 200
            if "check-missing" in url:
                resp.json.return_value = {"success": True, "result": ["abc123"]}
            else:
                resp.json.return_value = {"success": True, "result": {}}
            return resp

        def get(self, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"success": True, "result": {"jwt": "upload-jwt"}}
            return resp

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr("craftsman.publisher.privacy_policy.time.sleep", lambda *_: None)
    monkeypatch.setattr("craftsman.publisher.privacy_policy._cf_token", lambda: "token")
    monkeypatch.setattr("craftsman.publisher.privacy_policy._cf_account", lambda: "account")
    monkeypatch.setattr(
        "craftsman.publisher.privacy_policy.cf_pages_asset_hash",
        lambda content, filename="index.html": "abc123",
    )
    result = deploy_to_cloudflare_pages("timer-privacy", "<html/>", dry_run=False)
    assert result["ok"] is True
    assert attempts["n"] >= 2


def test_ensure_privacy_url_updates_store(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "craftsman.publisher.privacy_policy.deploy_to_cloudflare_pages",
        lambda *args, **kwargs: {"ok": True, "url": "https://timer-privacy.pages.dev/", "dry_run": True},
    )
    req = {
        "app": {"name": "Timer", "bundle_id": "com.test.timer"},
        "store": {"privacy_url": "https://example.com/privacy"},
    }
    result = ensure_privacy_url(req, tmp_path)
    assert result["ok"] is True
    assert req["store"]["privacy_url"] == "https://timer-privacy.pages.dev/"
    assert (tmp_path / "privacy" / "index.html").is_file()

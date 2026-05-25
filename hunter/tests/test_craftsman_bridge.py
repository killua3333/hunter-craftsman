import pytest

from hunter.integrations import build_requirement_from_blueprint
from hunter.integrations.craftsman import _http_json, _with_retry
from tests.conftest import sample_blueprint


def test_build_requirement_from_blueprint():
    blueprint = sample_blueprint()
    req = build_requirement_from_blueprint(blueprint, opportunity_id="focus-001")

    assert req["opportunity_id"] == "focus-001"
    assert req["schema_version"] == "1.0"
    assert req["platform"]["target"] == "android"
    assert req["app"]["name"] == "离线番茄钟"
    assert req["app"]["application_id"] == req["app"]["bundle_id"]
    assert req["app"]["min_android_sdk"] == "24"
    assert req["core_logic"]["persistence"] == "UserDefaults"
    assert req["ui_layout"]["navigation"] == "stack"
    assert req["data_quality"] == "assumption"
    assert len(req["evidence"]) == 1
    assert "accent_color" not in req["branding"]


def test_build_requirement_fallback_uses_shared_preferences_for_android():
    from hunter.schemas import AppOpportunityBlueprint

    blueprint = AppOpportunityBlueprint.model_construct(
        accepted=True,
        app_name="离线计时",
        core_logic="本地倒计时",
        ui_layout="单屏",
        keywords=["计时"],
        requirement=None,
    )
    req = build_requirement_from_blueprint(blueprint, opportunity_id="android-fallback")
    assert req["platform"]["target"] == "android"
    assert req["core_logic"]["persistence"] == "SharedPreferences"


def test_rejected_blueprint_cannot_build_requirement():
    from hunter.schemas import AppOpportunityBlueprint

    blueprint = AppOpportunityBlueprint(
        accepted=False,
        rejection_reason="需要后端账号系统",
    )
    with pytest.raises(ValueError, match="rejected"):
        build_requirement_from_blueprint(blueprint)


def test_http_json_passes_api_token(monkeypatch):
    monkeypatch.setenv("CRAFTSMAN_API_TOKEN", "token-123")
    monkeypatch.setenv("CRAFTSMAN_CONTRACT_VERSION", "1.0")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok":true}'

    captured = {}

    def fake_urlopen(request, timeout):
        captured["token"] = request.headers.get("X-api-token")
        captured["contract"] = request.headers.get("X-contract-version")
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    body = _http_json(
        url="http://localhost/v1/test",
        body=None,
        method="GET",
        timeout_seconds=1.0,
    )
    assert body["ok"] is True
    assert captured["token"] == "token-123"
    assert captured["contract"] == "1.0"


def test_http_json_detects_contract_version_mismatch(monkeypatch):
    monkeypatch.setenv("CRAFTSMAN_CONTRACT_VERSION", "1.0")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok":true,"contract_version":"2.0"}'

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _Resp())
    with pytest.raises(RuntimeError, match="contract version mismatch"):
        _http_json(
            url="http://localhost/v1/test",
            body=None,
            method="GET",
            timeout_seconds=1.0,
        )


def test_with_retry_only_for_transport_errors():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("craftsman unreachable: connection reset")
        return {"ok": True}

    result = _with_retry(flaky, attempts=2)
    assert result["ok"] is True
    assert calls["n"] == 2


def test_with_retry_skips_non_transport_runtime_error():
    calls = {"n": 0}

    def terminal():
        calls["n"] += 1
        raise RuntimeError("validation failed")

    with pytest.raises(RuntimeError, match="validation failed"):
        _with_retry(terminal, attempts=3)
    assert calls["n"] == 1

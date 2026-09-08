import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "hunter" / "tools" / "play_scraper.py"
SPEC = importlib.util.spec_from_file_location("play_scraper_under_test", MODULE_PATH)
play_scraper = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(play_scraper)


def test_ensure_play_proxy_does_not_inject_default_local_proxy(monkeypatch):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(key, raising=False)

    play_scraper._ensure_play_proxy()

    assert not play_scraper.os.environ.get("HTTP_PROXY")
    assert not play_scraper.os.environ.get("HTTPS_PROXY")


def test_ensure_play_proxy_normalizes_lowercase_proxy(monkeypatch):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("https_proxy", "http://proxy.example.com:8080")

    play_scraper._ensure_play_proxy()

    assert play_scraper.os.environ.get("HTTPS_PROXY") == "http://proxy.example.com:8080"
    assert play_scraper.os.environ.get("HTTP_PROXY") == "http://proxy.example.com:8080"


def test_play_access_error_mentions_explicit_proxy_only_when_needed(monkeypatch):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(key, raising=False)

    payload = json.loads(play_scraper._play_access_error("Play Store 搜索失败", RuntimeError("timeout"), query="timer"))

    assert "无需配置代理" in payload["error"]
    assert payload["query"] == "timer"


def test_retry_play_request_recovers_from_transient_failure(monkeypatch):
    monkeypatch.setattr(play_scraper.time, "sleep", lambda _seconds: None)
    calls = []

    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionResetError("temporary reset")
        return ["app"]

    assert play_scraper._retry_play_request(operation) == ["app"]
    assert len(calls) == 3


def test_retry_play_request_preserves_final_error(monkeypatch):
    monkeypatch.setattr(play_scraper.time, "sleep", lambda _seconds: None)

    def operation():
        raise RuntimeError("last network error")

    try:
        play_scraper._retry_play_request(operation)
    except RuntimeError as exc:
        assert str(exc) == "last network error"
    else:
        raise AssertionError("expected final request error")

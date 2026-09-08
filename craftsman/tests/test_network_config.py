from craftsman import config


def test_network_environment_keeps_dashboard_local(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "example.test")
    monkeypatch.setattr(config.settings, "no_proxy", "127.0.0.1,localhost")

    config._configure_network_environment()

    entries = config.os.environ["NO_PROXY"].split(",")
    assert "example.test" in entries
    assert "127.0.0.1" in entries
    assert "localhost" in entries
    assert config.os.environ["no_proxy"] == config.os.environ["NO_PROXY"]


def test_network_environment_exports_configured_proxy(monkeypatch):
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.setattr(config.settings, "http_proxy", "http://proxy.test:8080")
    monkeypatch.setattr(config.settings, "https_proxy", "http://proxy.test:8080")

    config._configure_network_environment()

    assert config.os.environ["HTTP_PROXY"] == "http://proxy.test:8080"
    assert config.os.environ["HTTPS_PROXY"] == "http://proxy.test:8080"

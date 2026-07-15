from craftsman.runtime.backends import (
    _java_proxy_options,
    _merge_java_tool_options,
    select_execution_backend,
)




def test_select_backend_defaults_android(monkeypatch):
    monkeypatch.setattr("craftsman.runtime.backends.choose_backend_target", lambda: "local")
    monkeypatch.setattr("craftsman.runtime.backends.xcode_tool.is_macos_with_xcode", lambda: False)
    monkeypatch.setattr("craftsman.runtime.backends.should_use_docker_backend", lambda: False)
    backend = select_execution_backend({})
    assert backend.mode == "android_gradle"


def test_select_backend_ios_falls_back_to_demo_without_xcode(monkeypatch):
    monkeypatch.setattr("craftsman.runtime.backends.choose_backend_target", lambda: "local")
    monkeypatch.setattr("craftsman.runtime.backends.xcode_tool.is_macos_with_xcode", lambda: False)
    backend = select_execution_backend({"platform": {"target": "ios"}})
    assert backend.mode == "demo"


def test_java_proxy_options_uses_actual_http_proxy():
    options = _java_proxy_options("http://proxy.example.com:8888")
    assert options == (
        "-Dhttps.proxyHost=proxy.example.com -Dhttps.proxyPort=8888 "
        "-Dhttp.proxyHost=proxy.example.com -Dhttp.proxyPort=8888"
    )


def test_java_proxy_options_supports_socks_proxy():
    options = _java_proxy_options("socks5://127.0.0.1:1090")
    assert options == "-DsocksProxyHost=127.0.0.1 -DsocksProxyPort=1090"


def test_java_proxy_options_ignores_invalid_proxy_values():
    assert _java_proxy_options("not-a-valid-proxy") is None


def test_merge_java_tool_options_preserves_existing_flags():
    merged = _merge_java_tool_options("-Xmx1g", "-Dhttp.proxyHost=proxy.example.com -Dhttp.proxyPort=8888")
    assert merged == "-Xmx1g -Dhttp.proxyHost=proxy.example.com -Dhttp.proxyPort=8888"

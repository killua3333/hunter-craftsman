from craftsman.runtime.backends import select_execution_backend


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

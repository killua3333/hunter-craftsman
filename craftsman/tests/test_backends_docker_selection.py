from craftsman.runtime.backends import select_execution_backend


def test_select_backend_prefers_docker_when_available(monkeypatch):
    monkeypatch.setattr("craftsman.runtime.backends.choose_backend_target", lambda: "local")
    monkeypatch.setattr("craftsman.runtime.backends.xcode_tool.is_macos_with_xcode", lambda: False)
    monkeypatch.setattr("craftsman.runtime.backends.should_use_docker_backend", lambda: True)
    backend = select_execution_backend({})
    assert backend.mode == "android_gradle_docker"


def test_select_backend_android_local_when_no_docker(monkeypatch):
    monkeypatch.setattr("craftsman.runtime.backends.choose_backend_target", lambda: "local")
    monkeypatch.setattr("craftsman.runtime.backends.xcode_tool.is_macos_with_xcode", lambda: False)
    monkeypatch.setattr("craftsman.runtime.backends.should_use_docker_backend", lambda: False)
    backend = select_execution_backend({})
    assert backend.mode == "android_gradle"

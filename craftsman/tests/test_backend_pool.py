from craftsman.config import settings
from craftsman.runtime.pool import choose_backend_target, reset_backend_pool_cursor


def test_round_robin_backend_pool(monkeypatch):
    monkeypatch.setattr(settings, "native_backend_pool", "mac-a,mac-b")
    monkeypatch.setattr(settings, "native_backend_pool_strategy", "round_robin")
    reset_backend_pool_cursor()
    first = choose_backend_target()
    second = choose_backend_target()
    third = choose_backend_target()
    assert first == "mac-a"
    assert second == "mac-b"
    assert third == "mac-a"

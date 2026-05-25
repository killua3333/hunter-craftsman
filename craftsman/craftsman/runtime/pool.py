from __future__ import annotations

from threading import Lock

from craftsman.config import settings

_LOCK = Lock()
_ROUND_ROBIN_IDX = 0


def backend_pool_targets() -> list[str]:
    targets = [item.strip() for item in settings.native_backend_pool.split(",") if item.strip()]
    return targets or ["local-macos"]


def choose_backend_target() -> str:
    global _ROUND_ROBIN_IDX
    strategy = settings.native_backend_pool_strategy.strip().lower()
    targets = backend_pool_targets()
    if strategy != "round_robin":
        return targets[0]
    with _LOCK:
        target = targets[_ROUND_ROBIN_IDX % len(targets)]
        _ROUND_ROBIN_IDX += 1
    return target


def reset_backend_pool_cursor() -> None:
    global _ROUND_ROBIN_IDX
    with _LOCK:
        _ROUND_ROBIN_IDX = 0

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any

from craftsman.config import settings

_WINDOW: deque[dict[str, Any]] = deque()
_LOCK = Lock()


def reset_alert_state() -> None:
    with _LOCK:
        _WINDOW.clear()


def evaluate_run_alerts(
    *,
    run_id: str,
    opportunity_id: str,
    revision: int,
    status: str,
    total_duration_seconds: float,
    failure_class: str | None,
) -> list[dict[str, Any]]:
    timeout_like = (failure_class or "").lower().find("timeout") >= 0
    near_timeout = total_duration_seconds >= (
        settings.max_implementation_seconds * settings.alert_duration_threshold_ratio
    )
    is_timeout = timeout_like or near_timeout
    is_failed = status in {"failed", "implementation_failed"}

    with _LOCK:
        _WINDOW.append({"failed": is_failed, "timeout": is_timeout})
        while len(_WINDOW) > max(settings.alert_window_size, 1):
            _WINDOW.popleft()

        sample_count = len(_WINDOW)
        if sample_count < max(settings.alert_min_samples, 1):
            return []

        failed_count = sum(1 for item in _WINDOW if item["failed"])
        timeout_count = sum(1 for item in _WINDOW if item["timeout"])
        failure_rate = failed_count / sample_count
        timeout_rate = timeout_count / sample_count

    alerts: list[dict[str, Any]] = []
    if failure_rate >= settings.alert_failure_rate_threshold:
        alerts.append(
            {
                "type": "failure_rate_spike",
                "run_id": run_id,
                "opportunity_id": opportunity_id,
                "revision": revision,
                "window_size": sample_count,
                "failed_count": failed_count,
                "failure_rate": round(failure_rate, 4),
                "threshold": settings.alert_failure_rate_threshold,
            }
        )
    if timeout_rate >= settings.alert_timeout_rate_threshold:
        alerts.append(
            {
                "type": "timeout_rate_spike",
                "run_id": run_id,
                "opportunity_id": opportunity_id,
                "revision": revision,
                "window_size": sample_count,
                "timeout_count": timeout_count,
                "timeout_rate": round(timeout_rate, 4),
                "threshold": settings.alert_timeout_rate_threshold,
            }
        )
    return alerts

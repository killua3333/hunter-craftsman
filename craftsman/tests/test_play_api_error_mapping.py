from __future__ import annotations

from craftsman.publisher.play_client import map_play_api_error
from craftsman.publisher.preflight import (
    _failure_class_from_play_message,
    _operator_action_from_play_message,
)


class _PlayError(Exception):
    def __init__(self, message: str, content: bytes) -> None:
        super().__init__(message)
        self.content = content


def test_service_disabled_is_not_misreported_as_release_permission() -> None:
    exc = _PlayError(
        "<HttpError 403>",
        b'{"error":{"status":"PERMISSION_DENIED","details":[{"reason":"SERVICE_DISABLED",'
        b'"metadata":{"service":"androidpublisher.googleapis.com"}}]}}',
    )

    message = map_play_api_error(exc)

    assert "Android Developer API is disabled" in message
    assert _failure_class_from_play_message(message) == "play_api_disabled"
    assert "Google Cloud" in _operator_action_from_play_message(message)


def test_generic_403_remains_a_play_console_permission_error() -> None:
    message = map_play_api_error(Exception("403 forbidden: caller lacks app access"))

    assert "Release manager" in message
    assert _failure_class_from_play_message(message) == "service_account_permission"

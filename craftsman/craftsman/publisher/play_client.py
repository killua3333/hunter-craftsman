from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from craftsman.secrets import resolve_secret_value

PLAY_SCOPE = "https://www.googleapis.com/auth/androidpublisher"


def service_account_info() -> dict[str, Any] | None:
    raw = resolve_secret_value("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", None)
    if not raw:
        path = resolve_secret_value("GOOGLE_PLAY_SERVICE_ACCOUNT_FILE", None)
        if path and Path(path).is_file():
            raw = Path(path).read_text(encoding="utf-8")
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def build_android_publisher_service():
    """Build Google Play Android Publisher API v3 client."""
    info = service_account_info()
    if info is None:
        raise RuntimeError("GOOGLE_PLAY service account not configured")

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "google-api-python-client and google-auth required for live Play upload"
        ) from exc

    credentials = service_account.Credentials.from_service_account_info(info, scopes=[PLAY_SCOPE])
    return build("androidpublisher", "v3", credentials=credentials, cache_discovery=False)


def map_play_api_error(exc: Exception) -> str:
    """Turn Google API errors into operator-friendly messages."""
    message = str(exc)
    lower = message.lower()
    if "403" in message or "forbidden" in lower:
        return "Play API permission denied: grant service account Release manager in Play Console"
    if "404" in message or "not found" in lower:
        return "Play app not found: create the app in Console with matching package name first"
    if "version code" in lower and "already been used" in lower:
        return "versionCode conflict: bump version and retry"
    if "applicationnotfound" in lower.replace(" ", ""):
        return "package name not registered in Play Console"
    return message[:500]

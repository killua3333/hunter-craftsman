from __future__ import annotations

import os
from pathlib import Path

from craftsman.config import ROOT, settings


def _secret_file_value(name: str) -> str | None:
    base = Path(settings.secret_store_dir).expanduser()
    if not base.is_absolute():
        base = ROOT / base
    names = (name, f"{name}.txt", name.lower(), f"{name.lower()}.txt")
    for filename in names:
        candidate = base / filename
        if candidate.is_file():
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
    return None


def _clean(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def resolve_secret_value(env_name: str, current_value: str | None) -> str | None:
    provider = str(settings.secret_provider or "env_file_fallback").strip().lower()
    env_value = _clean(os.getenv(env_name))
    configured_value = _clean(current_value)
    file_value = _secret_file_value(env_name)

    if provider == "file":
        return file_value or configured_value or env_value
    if provider == "env":
        return env_value or configured_value
    return env_value or configured_value or file_value


def resolve_secret_path(env_name: str, current_value: str | None) -> Path | None:
    value = resolve_secret_value(env_name, current_value)
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()

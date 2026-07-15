from __future__ import annotations

import os
from pathlib import Path

from craftsman.config import settings


def _secret_file_value(name: str) -> str | None:
    base = Path(settings.secret_store_dir)
    candidate = base / name
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8").strip()
    return None


def resolve_secret_value(env_name: str, current_value: str | None) -> str | None:
    env_value = os.getenv(env_name)
    if env_value:
        return env_value.strip()
    if current_value:
        return current_value.strip()
    file_value = _secret_file_value(env_name)
    if file_value:
        return file_value
    return None


def resolve_secret_path(env_name: str, current_value: str | None) -> Path | None:
    value = resolve_secret_value(env_name, current_value)
    if not value:
        return None
    return Path(value).expanduser().resolve()

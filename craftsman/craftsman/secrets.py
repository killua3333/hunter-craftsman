from __future__ import annotations

from pathlib import Path

from craftsman.config import settings
from craftsman.config import ROOT


def _secret_file_candidates(env_name: str, root: Path) -> list[Path]:
    return [
        root / env_name,
        root / f"{env_name}.txt",
        root / env_name.lower(),
        root / f"{env_name.lower()}.txt",
    ]


def _read_secret_from_store(env_name: str) -> str | None:
    root = settings.secret_store_dir
    if not root.exists():
        return None
    for candidate in _secret_file_candidates(env_name, root):
        if candidate.exists() and candidate.is_file():
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
    return None


def resolve_secret_value(env_name: str, current_value: str | None) -> str | None:
    provider = settings.secret_provider.strip().lower()
    if provider not in {"env", "file", "env_file_fallback"}:
        provider = "env_file_fallback"

    if provider == "env":
        return current_value
    if provider == "file":
        return _read_secret_from_store(env_name)
    if current_value:
        return current_value
    return _read_secret_from_store(env_name)


def resolve_secret_path(env_name: str, current_value: str | None) -> Path | None:
    value = resolve_secret_value(env_name, current_value)
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    candidates = [
        ROOT / path,
        Path.cwd() / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return ROOT / path

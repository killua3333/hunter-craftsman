from __future__ import annotations

from pathlib import Path

from craftsman.config import ROOT

_PROMPTS_DIR = ROOT / "prompts"


def load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()

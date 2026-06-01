from __future__ import annotations

from pathlib import Path


def dashboard_html() -> str:
    path = Path(__file__).with_name("dashboard.html")
    return path.read_text(encoding="utf-8")

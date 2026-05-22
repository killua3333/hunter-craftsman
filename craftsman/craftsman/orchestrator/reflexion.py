from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from craftsman.config import settings
from craftsman.llm import fix_code_llm
from craftsman.tools.xcode_errors import parse_xcode_errors


def read_swift_sources(project_dir: Path) -> dict[str, str]:
    sources = project_dir / "Sources"
    files: dict[str, str] = {}
    if not sources.exists():
        return files
    for path in sources.glob("*.swift"):
        rel = f"Sources/{path.name}"
        files[rel] = path.read_text(encoding="utf-8")
    info = project_dir / "Info.plist"
    if info.exists():
        files["Info.plist"] = info.read_text(encoding="utf-8")
    return files


def write_files(project_dir: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = project_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def error_fingerprint(errors: list[dict[str, Any]]) -> str:
    return json.dumps(
        [(e.get("file"), e.get("line"), e.get("message")) for e in errors],
        sort_keys=True,
    )


def apply_fixes(
    req: dict[str, Any],
    project_dir: Path,
    parsed: dict[str, Any],
    round_num: int,
    previous_fp: str | None,
) -> tuple[bool, str | None]:
    errors = parsed.get("errors") or []
    if not errors:
        return False, previous_fp
    fp = error_fingerprint(errors)
    if fp == previous_fp:
        return False, fp

    files = read_swift_sources(project_dir)
    patched = fix_code_llm(req, files, errors, round_num)
    if patched:
        write_files(project_dir, patched)
        return True, fp

    # Rule-based fallback: undefined symbols — no-op; signing errors skip
    return False, fp


def save_build_log(workspace: Path, log: str) -> Path:
    path = workspace / "build.log"
    path.write_text(log, encoding="utf-8")
    (workspace / "build_errors.json").write_text(
        json.dumps(parse_xcode_errors(log), indent=2),
        encoding="utf-8",
    )
    return path

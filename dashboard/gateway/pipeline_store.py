"""Filesystem-backed pipeline_runs/ store (meta.json + hunter.jsonl)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from settings import settings


_PIPELINE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pipeline_runs_root() -> Path:
    root = settings.pipeline_runs_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validate_pipeline_id(pipeline_id: str) -> None:
    if not _PIPELINE_ID_RE.match(pipeline_id):
        raise ValueError(f"invalid pipeline_id: {pipeline_id!r}")


def list_pipeline_metas(*, limit: int = 50) -> list[dict[str, Any]]:
    root = pipeline_runs_root()
    rows: list[tuple[str, dict[str, Any]]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        meta_path = child / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append((meta.get("updated_at") or meta.get("created_at") or "", meta))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [meta for _, meta in rows[: max(limit, 1)]]


def load_meta(pipeline_id: str) -> dict[str, Any] | None:
    _validate_pipeline_id(pipeline_id)
    meta_path = pipeline_runs_root() / pipeline_id / "meta.json"
    if not meta_path.is_file():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))


def save_meta(pipeline_id: str, meta: dict[str, Any]) -> None:
    _validate_pipeline_id(pipeline_id)
    directory = pipeline_runs_root() / pipeline_id
    directory.mkdir(parents=True, exist_ok=True)
    meta["updated_at"] = _utc_now()
    (directory / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_hunter_events(
    pipeline_id: str,
    *,
    after_line: int = 0,
    limit: int = 500,
) -> tuple[list[dict[str, Any]], int]:
    _validate_pipeline_id(pipeline_id)
    events_path = pipeline_runs_root() / pipeline_id / "hunter.jsonl"
    if not events_path.is_file():
        return [], after_line
    lines = events_path.read_text(encoding="utf-8").splitlines()
    slice_lines = lines[after_line : after_line + limit]
    events: list[dict[str, Any]] = []
    for line in slice_lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    next_after = after_line + len(slice_lines)
    return events, next_after


def upsert_meta_from_run(
    *,
    run_id: str,
    release_id: str | None = None,
    mode: str = "manual",
) -> dict[str, Any]:
    """Create or update a minimal meta.json when only run_id is known."""
    pipeline_id = f"pl-run-{run_id[:24]}"
    _validate_pipeline_id(pipeline_id)
    directory = pipeline_runs_root() / pipeline_id
    directory.mkdir(parents=True, exist_ok=True)
    meta_path = directory / "meta.json"
    now = _utc_now()
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.setdefault("craftsman", {})["run_id"] = run_id
        if release_id:
            meta.setdefault("publisher", {})["release_id"] = release_id
        meta["updated_at"] = now
    else:
        meta = {
            "pipeline_id": pipeline_id,
            "created_at": now,
            "updated_at": now,
            "mode": mode,
            "question": None,
            "status": "unknown",
            "terminal": None,
            "hunter": {"events_file": f"pipeline_runs/{pipeline_id}/hunter.jsonl"},
            "craftsman": {
                "base_url": settings.craftsman_base_url,
                "run_id": run_id,
            },
            "publisher": {"release_id": release_id},
        }
        (directory / "hunter.jsonl").touch(exist_ok=True)

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def attach_release(pipeline_id: str, release_id: str) -> dict[str, Any] | None:
    """Attach a release_id to existing meta when discovered from feedback."""
    meta = load_meta(pipeline_id)
    if meta is None:
        return None
    publisher = meta.setdefault("publisher", {})
    if publisher.get("release_id") == release_id:
        return meta
    publisher["release_id"] = release_id
    save_meta(pipeline_id, meta)
    return meta

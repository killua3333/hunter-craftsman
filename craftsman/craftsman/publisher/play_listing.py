from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "zh-CN"


def _read_text(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def load_listing_metadata(metadata_dir: Path | None) -> dict[str, str]:
    if metadata_dir is None or not metadata_dir.is_dir():
        return {}
    return {
        "title": _read_text(metadata_dir / "name.txt"),
        "short_description": _read_text(metadata_dir / "subtitle.txt"),
        "full_description": _read_text(metadata_dir / "description.txt"),
        "keywords": _read_text(metadata_dir / "keywords.txt"),
    }


def sync_listing_to_edit(
    service,
    *,
    package_name: str,
    edit_id: str,
    metadata_dir: Path | None,
    language: str = DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    """Push store listing text fields into an open Play edit."""
    meta = load_listing_metadata(metadata_dir)
    if not meta.get("title") and not meta.get("full_description"):
        return {"skipped": True, "reason": "no listing metadata"}

    body: dict[str, str] = {}
    if meta.get("title"):
        body["title"] = meta["title"][:50]
    if meta.get("short_description"):
        body["shortDescription"] = meta["short_description"][:80]
    if meta.get("full_description"):
        body["fullDescription"] = meta["full_description"][:4000]

    if not body:
        return {"skipped": True, "reason": "empty listing body"}

    result = (
        service.edits()
        .listings()
        .update(packageName=package_name, editId=edit_id, language=language, body=body)
        .execute()
    )
    return {"skipped": False, "listing": result}


def sync_images_to_edit(
    service,
    *,
    package_name: str,
    edit_id: str,
    icon_path: Path | None,
    screenshot_paths: list[Path],
    language: str = DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    """Upload icon and phone screenshots when files exist."""
    from googleapiclient.http import MediaFileUpload

    uploaded: list[str] = []
    errors: list[str] = []

    def _upload(image_type: str, path: Path) -> None:
        if not path.is_file():
            return
        try:
            media = MediaFileUpload(str(path), mimetype="image/png", resumable=True)
            service.edits().images().upload(
                packageName=package_name,
                editId=edit_id,
                language=language,
                imageType=image_type,
                media_body=media,
            ).execute()
            uploaded.append(f"{image_type}:{path.name}")
        except Exception as exc:
            errors.append(f"{image_type}: {exc}")
            logger.warning("play image upload failed type=%s path=%s err=%s", image_type, path, exc)

    if icon_path is not None:
        _upload("icon", icon_path)

    for shot in screenshot_paths[:8]:
        _upload("phoneScreenshots", shot)

    return {"uploaded": uploaded, "errors": errors}

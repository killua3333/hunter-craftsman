from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def read_version_from_gradle(project_dir: Path) -> tuple[int, str]:
    gradle_file = project_dir / "app" / "build.gradle.kts"
    text = gradle_file.read_text(encoding="utf-8")
    code_match = re.search(r"versionCode\s*=\s*(\d+)", text)
    name_match = re.search(r'versionName\s*=\s*"([^"]*)"', text)
    version_code = int(code_match.group(1)) if code_match else 1
    version_name = name_match.group(1) if name_match else "1.0.0"
    return version_code, version_name


def write_version_to_gradle(project_dir: Path, *, version_code: int, version_name: str) -> None:
    gradle_file = project_dir / "app" / "build.gradle.kts"
    text = gradle_file.read_text(encoding="utf-8")
    if re.search(r"versionCode\s*=", text):
        text = re.sub(r"versionCode\s*=\s*\d+", f"versionCode = {version_code}", text, count=1)
    else:
        text = text.replace("defaultConfig {", f"defaultConfig {{\n        versionCode = {version_code}", 1)
    if re.search(r'versionName\s*=\s*"', text):
        text = re.sub(r'versionName\s*=\s*"[^"]*"', f'versionName = "{version_name}"', text, count=1)
    else:
        text = text.replace(
            f"versionCode = {version_code}",
            f"versionCode = {version_code}\n        versionName = \"{version_name}\"",
            1,
        )
    gradle_file.write_text(text, encoding="utf-8")


def _max_version_from_track(track_payload: dict[str, Any]) -> int:
    max_code = 0
    for release in track_payload.get("releases") or []:
        if not isinstance(release, dict):
            continue
        for raw_code in release.get("versionCodes") or []:
            try:
                max_code = max(max_code, int(raw_code))
            except (TypeError, ValueError):
                continue
    return max_code


def fetch_max_version_code_from_play(service, package_name: str, track: str) -> int | None:
    """Query Play for the highest versionCode on a track (uses a transient edit)."""
    edit = service.edits().insert(packageName=package_name, body={}).execute()
    edit_id = str(edit["id"])
    try:
        track_payload = (
            service.edits()
            .tracks()
            .get(packageName=package_name, editId=edit_id, track=track)
            .execute()
        )
        max_code = _max_version_from_track(track_payload)
        return max_code if max_code > 0 else None
    except Exception:
        return None
    finally:
        try:
            service.edits().delete(packageName=package_name, editId=edit_id).execute()
        except Exception:
            pass


def bump_version_for_release(
    project_dir: Path,
    *,
    package_name: str | None = None,
    track: str = "internal",
    dry_run: bool = False,
    service: Any | None = None,
) -> tuple[int, str, str]:
    """
    Ensure versionCode is greater than local file and Play track (if available).
    Returns (version_code, version_name, detail_message).
    """
    local_code, local_name = read_version_from_gradle(project_dir)
    remote_code = 0
    if not dry_run and service is not None and package_name:
        remote_code = fetch_max_version_code_from_play(service, package_name, track) or 0

    next_code = max(local_code, remote_code) + 1
    parts = local_name.split(".")
    if len(parts) >= 3 and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
        next_name = ".".join(parts)
    else:
        next_name = f"{local_name}.{next_code}"

    write_version_to_gradle(project_dir, version_code=next_code, version_name=next_name)
    detail = f"versionCode {local_code} -> {next_code}, versionName -> {next_name}"
    if remote_code:
        detail += f" (Play track max was {remote_code})"
    return next_code, next_name, detail

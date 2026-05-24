from __future__ import annotations

from pathlib import Path
from typing import Any

from craftsman.config import settings
from craftsman.publisher.models import ReleaseUploadResult
from craftsman.publisher.play_client import (
    build_android_publisher_service,
    map_play_api_error,
    service_account_info,
)
from craftsman.publisher.play_listing import sync_images_to_edit, sync_listing_to_edit


def upload_to_play(
    *,
    aab_path: Path,
    package_name: str,
    track: str | None = None,
    dry_run: bool | None = None,
    metadata_dir: Path | None = None,
    icon_path: Path | None = None,
    screenshot_paths: list[Path] | None = None,
) -> ReleaseUploadResult:
    """
    Upload AAB to Google Play via Edits API: listing → bundle → track → commit.
    Falls back to dry-run when PUBLISHER_DRY_RUN=true or service account missing.
    """
    effective_dry_run = settings.publisher_dry_run if dry_run is None else dry_run
    release_track = track or settings.android_release_track

    if effective_dry_run or service_account_info() is None:
        return ReleaseUploadResult(
            ok=True,
            track=release_track,
            message=(
                "dry-run upload accepted (configure GOOGLE_PLAY_SERVICE_ACCOUNT_FILE for live upload)"
            ),
            dry_run=True,
            store_response={
                "package_name": package_name,
                "aab": str(aab_path),
                "track": release_track,
            },
        )

    try:
        service = build_android_publisher_service()
    except RuntimeError as exc:
        return ReleaseUploadResult(
            ok=False,
            track=release_track,
            message=str(exc),
            store_response={"error": str(exc)},
        )

    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        return ReleaseUploadResult(
            ok=False,
            track=release_track,
            message="google-api-python-client not installed for live Play upload",
            store_response={"error": str(exc)},
        )

    shots = screenshot_paths or []
    store_response: dict[str, Any] = {"package_name": package_name, "track": release_track}

    try:
        edit = service.edits().insert(packageName=package_name, body={}).execute()
        edit_id = str(edit["id"])
        store_response["edit_id"] = edit_id

        listing_result = sync_listing_to_edit(
            service,
            package_name=package_name,
            edit_id=edit_id,
            metadata_dir=metadata_dir,
        )
        store_response["listing"] = listing_result

        images_result = sync_images_to_edit(
            service,
            package_name=package_name,
            edit_id=edit_id,
            icon_path=icon_path,
            screenshot_paths=shots,
        )
        store_response["images"] = images_result

        media = MediaFileUpload(str(aab_path), mimetype="application/octet-stream", resumable=True)
        bundle = (
            service.edits()
            .bundles()
            .upload(packageName=package_name, editId=edit_id, media_body=media)
            .execute()
        )
        version_code = str(bundle.get("versionCode") or "")
        store_response["bundle"] = {"versionCode": version_code}

        if not version_code:
            service.edits().delete(packageName=package_name, editId=edit_id).execute()
            return ReleaseUploadResult(
                ok=False,
                track=release_track,
                message="Play bundle upload returned no versionCode",
                store_response=store_response,
            )

        track_body = {
            "releases": [
                {
                    "status": "completed",
                    "versionCodes": [version_code],
                }
            ]
        }
        track_result = (
            service.edits()
            .tracks()
            .update(
                packageName=package_name,
                editId=edit_id,
                track=release_track,
                body=track_body,
            )
            .execute()
        )
        store_response["track_update"] = track_result

        commit = service.edits().commit(packageName=package_name, editId=edit_id).execute()
        store_response["commit"] = commit

        return ReleaseUploadResult(
            ok=True,
            track=release_track,
            message=f"published to {release_track} track (versionCode={version_code})",
            dry_run=False,
            store_response=store_response,
        )
    except Exception as exc:
        mapped = map_play_api_error(exc)
        store_response["error"] = mapped
        return ReleaseUploadResult(
            ok=False,
            track=release_track,
            message=mapped,
            store_response=store_response,
        )

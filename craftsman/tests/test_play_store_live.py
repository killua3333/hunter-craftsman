from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from craftsman.config import settings
from craftsman.publisher.android_version import (
    bump_version_for_release,
    read_version_from_gradle,
    write_version_to_gradle,
)
from craftsman.publisher.play_listing import load_listing_metadata, sync_listing_to_edit
from craftsman.publisher.play_store import upload_to_play


def test_read_write_version_gradle(tmp_path):
    project = tmp_path / "project"
    app = project / "app"
    app.mkdir(parents=True)
    gradle = app / "build.gradle.kts"
    gradle.write_text(
        'android { defaultConfig { versionCode = 3 versionName = "1.0.2" } }',
        encoding="utf-8",
    )
    code, name = read_version_from_gradle(project)
    assert code == 3
    assert name == "1.0.2"
    write_version_to_gradle(project, version_code=4, version_name="1.0.3")
    code2, name2 = read_version_from_gradle(project)
    assert code2 == 4
    assert name2 == "1.0.3"


def test_bump_version_local_only(tmp_path):
    project = tmp_path / "project"
    app = project / "app"
    app.mkdir(parents=True)
    (app / "build.gradle.kts").write_text(
        'android { defaultConfig { versionCode = 5 versionName = "1.0.0" } }',
        encoding="utf-8",
    )
    code, name, detail = bump_version_for_release(project, dry_run=True)
    assert code == 6
    assert "6" in detail


def test_load_listing_metadata(tmp_path):
    meta = tmp_path / "zh-CN"
    meta.mkdir()
    (meta / "name.txt").write_text("番茄钟", encoding="utf-8")
    (meta / "subtitle.txt").write_text("专注", encoding="utf-8")
    (meta / "description.txt").write_text("完整描述", encoding="utf-8")
    loaded = load_listing_metadata(meta)
    assert loaded["title"] == "番茄钟"
    assert loaded["short_description"] == "专注"


def test_sync_listing_to_edit_calls_api():
    service = MagicMock()
    service.edits.return_value.listings.return_value.update.return_value.execute.return_value = {
        "language": "zh-CN"
    }
    meta = Path("/tmp/meta")
    with patch(
        "craftsman.publisher.play_listing.load_listing_metadata",
        return_value={
            "title": "App",
            "short_description": "Sub",
            "full_description": "Full",
        },
    ):
        result = sync_listing_to_edit(
            service,
            package_name="com.test.app",
            edit_id="edit-1",
            metadata_dir=meta,
        )
    assert result["skipped"] is False
    service.edits.return_value.listings.return_value.update.assert_called_once()


def test_upload_to_play_live_success(monkeypatch, tmp_path):
    pytest.importorskip("googleapiclient")
    monkeypatch.setattr(settings, "publisher_dry_run", False)
    aab = tmp_path / "app-release.aab"
    aab.write_bytes(b"fake-aab")

    service = MagicMock()
    service.edits.return_value.insert.return_value.execute.return_value = {"id": "edit-99"}
    service.edits.return_value.bundles.return_value.upload.return_value.execute.return_value = {
        "versionCode": 42
    }
    service.edits.return_value.tracks.return_value.update.return_value.execute.return_value = {"track": "internal"}
    service.edits.return_value.commit.return_value.execute.return_value = {"id": "edit-99"}

    with patch("craftsman.publisher.play_store.service_account_info", return_value={"type": "service_account"}):
        with patch("craftsman.publisher.play_store.build_android_publisher_service", return_value=service):
            with patch("craftsman.publisher.play_store.sync_listing_to_edit", return_value={"skipped": True}):
                with patch("craftsman.publisher.play_store.sync_images_to_edit", return_value={"uploaded": []}):
                    with patch("googleapiclient.http.MediaFileUpload", MagicMock()):
                        result = upload_to_play(
                            aab_path=aab,
                            package_name="com.test.app",
                            track="internal",
                            dry_run=False,
                        )

    assert result.ok is True
    assert result.dry_run is False
    assert "42" in result.message
    service.edits.return_value.commit.assert_called_once()


def test_upload_to_play_maps_api_error(monkeypatch, tmp_path):
    pytest.importorskip("googleapiclient")
    monkeypatch.setattr(settings, "publisher_dry_run", False)
    aab = tmp_path / "app-release.aab"
    aab.write_bytes(b"fake-aab")

    service = MagicMock()
    service.edits.return_value.insert.return_value.execute.side_effect = Exception("403 Forbidden")

    with patch("craftsman.publisher.play_store.service_account_info", return_value={"type": "service_account"}):
        with patch("craftsman.publisher.play_store.build_android_publisher_service", return_value=service):
            with patch("googleapiclient.http.MediaFileUpload", MagicMock()):
                result = upload_to_play(
                    aab_path=aab,
                    package_name="com.test.app",
                    dry_run=False,
                )

    assert result.ok is False
    assert "permission" in result.message.lower()

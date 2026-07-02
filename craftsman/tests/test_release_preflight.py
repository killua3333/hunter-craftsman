from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from craftsman.config import settings
from craftsman.publisher.preflight import run_release_preflight


def _handoff(root: Path, *, run_id: str = "run-preflight") -> dict:
    workspace = root / run_id
    project = workspace / "project"
    app = project / "app"
    main = app / "src" / "main"
    main.mkdir(parents=True)
    (app / "build.gradle.kts").write_text('android { defaultConfig { versionCode = 1 versionName = "1.0.0" } }', encoding="utf-8")
    (main / "AndroidManifest.xml").write_text("<manifest/>", encoding="utf-8")
    (workspace / "manifest.json").write_text(json.dumps({"application_id": "com.example.preflight"}), encoding="utf-8")
    meta = project / "play" / "metadata" / "zh-CN"
    meta.mkdir(parents=True)
    for name in ("name.txt", "subtitle.txt", "description.txt", "keywords.txt"):
        (meta / name).write_text("Preflight", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    icon = artifacts / "icon.png"
    shot = artifacts / "screenshot-1.png"
    icon.write_bytes(b"icon")
    shot.write_bytes(b"shot")
    base = f"object://local/runs/{run_id}"
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "opportunity_id": "opp-preflight",
        "revision": 1,
        "platform": {"target": "android"},
        "app": {"name": "Preflight", "bundle_id": "com.example.preflight"},
        "release_bundle": {
            "project_path": f"{base}/project",
            "metadata_path": f"{base}/project/play/metadata/zh-CN",
            "icon": f"{base}/artifacts/icon.png",
            "screenshots": [f"{base}/artifacts/screenshot-1.png"],
        },
    }


def test_release_preflight_dry_run_checks_local_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root", tmp_path)
    handoff = _handoff(tmp_path)

    result = run_release_preflight(handoff, dry_run=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["package_name"] == "com.example.preflight"


def test_release_preflight_live_requires_service_account(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root", tmp_path)
    monkeypatch.setattr(settings, "google_play_service_account_file", None)
    monkeypatch.delenv("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_PLAY_SERVICE_ACCOUNT_FILE", raising=False)
    handoff = _handoff(tmp_path)

    result = run_release_preflight(handoff, dry_run=False)

    assert result["ok"] is False
    assert result["failure_class"] in {"signing_config", "service_account_permission"}


def test_release_preflight_classifies_play_package_not_created(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root", tmp_path)
    monkeypatch.setattr(settings, "android_keystore_path", str(tmp_path / "release.jks"))
    monkeypatch.setattr(settings, "android_keystore_password", "pw")
    monkeypatch.setattr(settings, "android_key_alias", "alias")
    monkeypatch.setattr(settings, "android_key_password", "pw")
    (tmp_path / "release.jks").write_bytes(b"keystore")
    handoff = _handoff(tmp_path)

    service = MagicMock()
    service.edits.return_value.insert.return_value.execute.side_effect = Exception("404 not found")

    result = run_release_preflight(handoff, dry_run=False, service=service)

    assert result["ok"] is False
    assert result["failure_class"] == "package_not_precreated"
    assert "Play Console" in result["operator_action"]

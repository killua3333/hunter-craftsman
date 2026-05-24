from __future__ import annotations

import json
from pathlib import Path

from craftsman.config import settings
from craftsman.publisher.android_build import build_release_aab
from craftsman.publisher.handoff import application_id, resolve_project_dir
from craftsman.publisher.orchestrator import run_android_release


def _sample_handoff(workspace_root: Path, *, run_id: str = "run-test") -> dict:
    workspace = workspace_root / run_id
    project = workspace / "project"
    app_dir = project / "app" / "src" / "main"
    app_dir.mkdir(parents=True)
    (project / "app" / "build.gradle.kts").write_text("", encoding="utf-8")
    (app_dir / "AndroidManifest.xml").write_text("<manifest/>", encoding="utf-8")
    (workspace / "manifest.json").write_text(
        json.dumps({"bundle_id": "com.test.publisher"}),
        encoding="utf-8",
    )
    metadata = project / "play" / "metadata" / "zh-CN"
    metadata.mkdir(parents=True)
    (metadata / "title.txt").write_text("Test App", encoding="utf-8")
    (metadata / "short_description.txt").write_text("Short", encoding="utf-8")
    (metadata / "full_description.txt").write_text("Full description", encoding="utf-8")

    base = f"object://local/runs/{run_id}"
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "opportunity_id": "opp-test",
        "revision": 1,
        "platform": {"target": "android"},
        "requirement_digest": "test-digest",
        "workspace": f"{base}",
        "release_bundle": {
            "project_path": f"{base}/project",
            "metadata_path": f"{base}/project/play/metadata/zh-CN",
            "icon": f"{base}/artifacts/icon.png",
            "screenshots": [f"{base}/artifacts/shot.png"],
        },
        "build_provenance": {
            "backend": "android_gradle",
            "backend_target": "android",
            "craftsman_version": "0.1.0",
            "codegen_model": "test-model",
            "platform_note": "test",
        },
        "compliance_metadata": {
            "subtitle": "Sub",
            "description": "Desc",
            "keywords": ["test"],
            "privacy_url": "https://com-test-publisher.pages.dev/privacy",
        },
        "agent_b_status": "implementation_complete",
    }


def test_handoff_resolves_project_dir(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    monkeypatch.setattr(settings, "workspace_root", root)
    handoff = _sample_handoff(root, run_id="abc123")
    project = resolve_project_dir(handoff)
    assert project is not None
    assert project.name == "project"
    assert application_id(handoff) == "com.test.publisher"


def test_build_release_aab_dry_run(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    monkeypatch.setattr(settings, "workspace_root", root)
    handoff = _sample_handoff(root)
    project = resolve_project_dir(handoff)
    assert project is not None
    result = build_release_aab(project, dry_run=True)
    assert result.ok is True
    assert result.aab_path
    assert Path(result.aab_path).is_file()


def test_run_android_release_dry_run(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    monkeypatch.setattr(settings, "workspace_root", root)
    monkeypatch.setattr(settings, "publisher_dry_run", True)
    handoff = _sample_handoff(root)
    result = run_android_release(handoff, release_id="rel-test", dry_run=True)
    assert result["agent_c_status"] == "dry_run_complete"
    assert result["platform_target"] == "android"
    assert result["release_bundle"]["aab_path"]
    assert result["upload"]["dry_run"] is True
    assert result.get("setup_sheet")
    assert "com.test.publisher" in result["setup_sheet"]
    assert (root / "run-test" / "play_console_setup.txt").is_file()


def test_run_android_release_rejects_ios(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    monkeypatch.setattr(settings, "workspace_root", root)
    handoff = _sample_handoff(root)
    handoff["platform"] = {"target": "ios"}
    result = run_android_release(handoff, release_id="rel-ios")
    assert result["agent_c_status"] == "failed"
    assert "not android" in " ".join(result.get("reasons") or []).lower()

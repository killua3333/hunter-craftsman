"""End-to-end verification helpers for Agent C live publish (internal track).

Run mocked tests via pytest. For live Console verification after configuring secrets,
see docs/play-console-setup-checklist.md section 验收标准.
"""

from __future__ import annotations

from pathlib import Path

from craftsman.config import settings
from craftsman.publisher.android_version import bump_version_for_release, read_version_from_gradle
from craftsman.publisher.orchestrator import run_android_release
from craftsman.publisher.play_client import service_account_info


def _sample_handoff(workspace_root: Path, *, run_id: str = "e2e-run") -> dict:
    import json

    workspace = workspace_root / run_id
    project = workspace / "project"
    app_dir = project / "app" / "src" / "main"
    app_dir.mkdir(parents=True)
    (project / "app" / "build.gradle.kts").write_text(
        'android { defaultConfig { versionCode = 1 versionName = "1.0.0" } }',
        encoding="utf-8",
    )
    (app_dir / "AndroidManifest.xml").write_text("<manifest/>", encoding="utf-8")
    (workspace / "manifest.json").write_text(
        json.dumps({"bundle_id": "com.e2e.testapp"}),
        encoding="utf-8",
    )
    metadata = project / "play" / "metadata" / "zh-CN"
    metadata.mkdir(parents=True)
    (metadata / "name.txt").write_text("E2E App", encoding="utf-8")
    (metadata / "subtitle.txt").write_text("Test", encoding="utf-8")
    (metadata / "description.txt").write_text("E2E description", encoding="utf-8")
    base = f"object://local/runs/{run_id}"
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "opportunity_id": "opp-e2e",
        "revision": 1,
        "platform": {"target": "android"},
        "requirement_digest": "e2e-test-digest-0123456789abcdef",
        "workspace": base,
        "release_bundle": {
            "project_path": f"{base}/project",
            "metadata_path": f"{base}/project/play/metadata/zh-CN",
            "icon": f"{base}/artifacts/icon.png",
            "screenshots": [],
        },
        "build_provenance": {
            "backend": "android_gradle",
            "backend_target": "android",
            "craftsman_version": "0.1.0",
            "codegen_model": "test",
            "platform_note": "e2e",
        },
        "compliance_metadata": {
            "subtitle": "Sub",
            "description": "Desc",
            "keywords": ["test"],
            "privacy_url": "https://com-e2e-testapp.pages.dev/privacy",
        },
        "agent_b_status": "implementation_complete",
    }


def verify_live_publish_readiness() -> dict[str, bool]:
    """Check whether local env is ready for live publish (non-destructive)."""
    return {
        "publisher_dry_run_disabled": not settings.publisher_dry_run,
        "play_service_account": service_account_info() is not None,
        "gradle_wrapper_in_template": (
            Path(__file__).resolve().parents[1] / "templates" / "android-app" / "gradlew.bat"
        ).is_file(),
    }


def test_e2e_dry_run_pipeline(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    monkeypatch.setattr(settings, "workspace_root", root)
    monkeypatch.setattr(settings, "publisher_dry_run", True)
    handoff = _sample_handoff(root)
    result = run_android_release(handoff, release_id="rel-e2e", dry_run=True)
    assert result["agent_c_status"] == "dry_run_complete"
    assert result["upload"]["dry_run"] is True


def test_version_bump_integration(tmp_path):
    project = tmp_path / "project"
    app = project / "app"
    app.mkdir(parents=True)
    (app / "build.gradle.kts").write_text(
        'android { defaultConfig { versionCode = 10 versionName = "1.0.0" } }',
        encoding="utf-8",
    )
    code, _, _ = bump_version_for_release(project, dry_run=True)
    assert read_version_from_gradle(project)[0] == 11
    assert code == 11

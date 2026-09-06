import json
from pathlib import Path

from craftsman.config import settings
from craftsman.orchestrator.pipeline import run_implementation
from craftsman.runtime.interfaces import BuildResult
from craftsman.store.db import RunStore

SAMPLE = Path(__file__).parent.parent / "examples" / "requirement.sample.json"


def test_windows_demo_mode_generates_artifacts(tmp_path, monkeypatch):
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))

    monkeypatch.setattr(settings, "skip_xcodebuild", True)
    monkeypatch.setattr(settings, "skip_fastlane", True)
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "workspace")
    monkeypatch.setattr(settings, "callback_dir", tmp_path / "callbacks")

    store = RunStore(db_path=tmp_path / "runs.db")
    run_id = store.create_run(
        opportunity_id=req["opportunity_id"],
        revision=req["revision"],
        requirement=req,
    )

    fb = run_implementation(store, run_id)
    payload = fb.to_agent_a_dict()

    assert payload["agent_b_status"] == "needs_polish"
    assert payload.get("verification") == "demo"
    assert payload["quality_report"]["release_ready"] is False
    assert "native_verification_missing" in payload["quality_report"]["failure_classes"]
    artifacts = payload["artifacts"]
    assert artifacts["workspace"].startswith(("object://", "file://"))
    assert artifacts["demo_html"].startswith(("object://", "file://"))
    assert artifacts["preview_html"].startswith(("object://", "file://"))
    local = artifacts["local_paths"]
    assert Path(local["demo_html"]).is_file()
    assert Path(local["preview_html"]).is_file()
    preview = Path(local["preview_html"]).read_text(encoding="utf-8").lower()
    assert "<script" in preview
    assert Path(local["icon"]).is_file()
    assert len(artifacts["screenshots"]) >= 1
    assert len(local["screenshots"]) >= 1
    assert "release_handoff" in payload
    assert payload["release_handoff"]["platform"]["target"] == "android"


def test_android_build_exports_debug_apk_without_agent_c(tmp_path, monkeypatch):
    class SuccessfulAndroidBackend:
        mode = "android_gradle"
        target = "test-android"

        def can_compile(self):
            return True

        def compile(self, project_dir, scheme):
            apk = project_dir / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
            apk.parent.mkdir(parents=True, exist_ok=True)
            apk.write_bytes(b"assembled-debug-apk")
            return BuildResult(ok=True, mode=self.mode, exit_code=0, log="BUILD SUCCESSFUL")

        def platform_note(self):
            return "test Android backend"

    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "workspace")
    monkeypatch.setattr(settings, "callback_dir", tmp_path / "callbacks")
    monkeypatch.setattr(settings, "android_smoke_test", "off")
    monkeypatch.setattr(
        "craftsman.orchestrator.pipeline.select_execution_backend",
        lambda requirement: SuccessfulAndroidBackend(),
    )

    store = RunStore(db_path=tmp_path / "runs.db")
    run_id = store.create_run(
        opportunity_id=req["opportunity_id"],
        revision=req["revision"],
        requirement=req,
    )

    feedback = run_implementation(store, run_id)
    payload = feedback.to_agent_a_dict()
    artifacts = payload["artifacts"]
    exported = Path(artifacts["local_paths"]["apk"])

    assert payload["verification"] == "verified"
    assert exported == settings.workspace_root / run_id / "artifacts" / "app-debug.apk"
    assert exported.read_bytes() == b"assembled-debug-apk"
    assert artifacts["apk"].endswith("/artifacts/app-debug.apk")
    assert payload["release_handoff"]["release_bundle"]["apk_path"] == artifacts["apk"]

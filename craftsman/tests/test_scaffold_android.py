import json
from pathlib import Path

from craftsman.generator.scaffold import scaffold_project


def test_android_manifest_includes_application_id(tmp_path, monkeypatch):
    monkeypatch.setattr("craftsman.generator.scaffold.generate_code_llm", lambda req, platform="ios": None)
    req = {
        "opportunity_id": "opp-1",
        "revision": 1,
        "app": {
            "name": "Timer",
            "bundle_id": "com.hunter.timer",
            "application_id": "com.hunter.timer.prod",
        },
        "platform": {"target": "android"},
        "features": [],
        "core_logic": {"persistence": "none"},
    }
    workspace = tmp_path / "ws"
    scaffold_project(workspace, req)
    manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["application_id"] == "com.hunter.timer.prod"
    gradle = (workspace / "project/app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'namespace = "com.craftsman"' in gradle
    assert 'applicationId = "com.hunter.timer.prod"' in gradle

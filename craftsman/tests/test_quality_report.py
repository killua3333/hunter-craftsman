from __future__ import annotations

from pathlib import Path

from craftsman.generator.scaffold import repair_android_codegen_for_quality
from craftsman.orchestrator.quality import evaluate_app_quality, write_implementation_plan


def _android_project(tmp_path: Path, main_activity: str) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    project = workspace / "project"
    src = project / "app" / "src" / "main" / "java" / "com" / "example"
    src.mkdir(parents=True)
    (src / "MainActivity.kt").write_text(main_activity, encoding="utf-8")
    metadata = project / "play" / "metadata" / "zh-CN"
    metadata.mkdir(parents=True)
    for name in ("name.txt", "subtitle.txt", "description.txt", "keywords.txt"):
        (metadata / name).write_text("Local focus timer", encoding="utf-8")
    return workspace, project, metadata


def test_write_implementation_plan_limits_scope(tmp_path):
    requirement = {
        "app": {"name": "Focus Timer"},
        "features": [
            {"id": "timer", "title": "Focus timer"},
            {"id": "history", "title": "Session history"},
            {"id": "settings", "title": "Timer settings"},
            {"id": "extra", "title": "Extra feature"},
        ],
        "core_logic": {"persistence": "SharedPreferences"},
    }

    plan = write_implementation_plan(tmp_path, requirement)

    assert plan["main_flow"] == "Focus timer"
    assert plan["core_features"] == ["Focus timer", "Session history", "Timer settings"]
    assert (tmp_path / "implementation_plan.json").is_file()


def test_quality_report_release_ready_for_interactive_local_app(tmp_path):
    workspace, project, metadata = _android_project(
        tmp_path,
        """
        package com.example
        fun MainActivity() {
            setContent {
                val value = rememberSaveable { mutableStateOf("Focus timer") }
                TextField(value = value.value, onValueChange = { value.value = it })
                Button(onClick = { value.value = "Session history" }) { Text("Start focus timer") }
            }
        }
        """,
    )
    icon = workspace / "icon.png"
    shot = workspace / "shot.png"
    icon.write_bytes(b"icon")
    shot.write_bytes(b"shot")

    report = evaluate_app_quality(
        backend_mode="android_gradle",
        compile_exit_code=0,
        project_dir=project,
        workspace=workspace,
        requirement={"app": {"name": "Focus Timer"}, "features": [{"title": "Focus timer"}]},
        icon_path=icon,
        screenshots=[str(shot)],
        metadata_root=metadata,
        verification="verified",
    )

    assert report["quality_score"] >= 75
    assert report["release_ready"] is True
    assert "button" in report["main_interactions"]
    assert report["persistence_evidence"]


def test_quality_report_blocks_empty_ui(tmp_path):
    workspace, project, metadata = _android_project(
        tmp_path,
        "package com.example\nclass MainActivity",
    )
    icon = workspace / "icon.png"
    shot = workspace / "shot.png"
    icon.write_bytes(b"icon")
    shot.write_bytes(b"shot")

    report = evaluate_app_quality(
        backend_mode="android_gradle",
        compile_exit_code=0,
        project_dir=project,
        workspace=workspace,
        requirement={"app": {"name": "Focus Timer"}, "features": [{"title": "Focus timer"}]},
        icon_path=icon,
        screenshots=[str(shot)],
        metadata_root=metadata,
        verification="verified",
    )

    assert report["release_ready"] is False
    assert "empty_ui" in report["failure_classes"]


def test_quality_report_penalizes_missing_persistence(tmp_path):
    workspace, project, metadata = _android_project(
        tmp_path,
        """
        package com.example
        fun MainActivity() {
            setContent {
                Button(onClick = {}) { Text("Focus timer") }
            }
        }
        """,
    )
    icon = workspace / "icon.png"
    shot = workspace / "shot.png"
    icon.write_bytes(b"icon")
    shot.write_bytes(b"shot")

    report = evaluate_app_quality(
        backend_mode="android_gradle",
        compile_exit_code=0,
        project_dir=project,
        workspace=workspace,
        requirement={"app": {"name": "Focus Timer"}, "features": [{"title": "Focus timer"}]},
        icon_path=icon,
        screenshots=[str(shot)],
        metadata_root=metadata,
        verification="verified",
    )

    assert "no_persistence" in report["failure_classes"]
    assert report["quality_score"] < 100


def test_repair_android_codegen_for_quality_rewrites_main_activity(tmp_path, monkeypatch):
    monkeypatch.setattr("craftsman.generator.scaffold.generate_code_llm", lambda *args, **kwargs: None)
    workspace, project, _metadata = _android_project(
        tmp_path,
        "package com.example\nclass MainActivity",
    )

    changed = repair_android_codegen_for_quality(
        project,
        {
            "app": {"name": "Focus Timer", "bundle_id": "com.example.focus"},
            "features": [{"id": "timer", "title": "Focus timer", "items": ["start", "history"]}],
            "core_logic": {"persistence": "SharedPreferences"},
            "branding": {"primary_color": "#3366FF"},
        },
        {"failure_classes": ["empty_ui", "weak_core_flow"], "repair_suggestions": ["add controls"]},
    )

    main = project / "app" / "src" / "main" / "java" / "com" / "craftsman" / "MainActivity.kt"
    text = main.read_text(encoding="utf-8")
    assert changed is True
    assert "setContent" in text
    assert "Button(" in text or ".clickable" in text
    assert "remember" in text or "mutableState" in text

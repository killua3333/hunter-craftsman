from __future__ import annotations

from pathlib import Path

from craftsman.generator.scaffold import repair_android_codegen_for_quality
from craftsman.orchestrator.quality import evaluate_app_quality, write_implementation_plan


DEVICE_VERIFIED = {
    "status": "launch_verified",
    "launch_verified": True,
    "core_flow_verified": False,
    "persistence_verified": False,
    "device_screenshots": [],
}


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
        device_acceptance_report=DEVICE_VERIFIED,
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
        device_acceptance_report=DEVICE_VERIFIED,
    )

    assert report["release_ready"] is False
    assert "empty_ui" in report["failure_classes"]


def test_quality_report_blocks_compile_only_without_device_launch(tmp_path):
    workspace, project, metadata = _android_project(
        tmp_path,
        """
        package com.example
        fun MainActivity() {
            setContent {
                val value = rememberSaveable { mutableStateOf("Focus timer") }
                TextField(value = value.value, onValueChange = { value.value = it })
                Button(onClick = { value.value = "Saved" }) { Text("Start focus timer") }
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
        device_acceptance_report={"status": "unavailable", "launch_verified": False},
    )

    assert report["quality_score"] == 74
    assert report["release_ready"] is False
    assert "device_verification_missing" in report["failure_classes"]
    assert report["store_screenshot_source"] == "generated_marketing_mockup"


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
        device_acceptance_report=DEVICE_VERIFIED,
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


def test_quality_report_v2_contains_subscores_and_notes(tmp_path):
    workspace, project, metadata = _android_project(
        tmp_path,
        """
        package com.example
        fun MainActivity() {
            setContent {
                val value = rememberSaveable { mutableStateOf("Focus timer") }
                if (value.value.isEmpty()) { Text("No items yet") }
                TextField(value = value.value, onValueChange = { value.value = it })
                Button(onClick = { value.value = "Saved result" }) { Text("Start focus timer") }
                Text("Session history saved")
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
        device_acceptance_report=DEVICE_VERIFIED,
    )

    assert report["schema_version"] == 2
    assert report["core_flow_score"] >= 75
    assert report["ui_completeness_score"] >= 75
    assert report["persistence_score"] >= 75
    assert report["store_asset_score"] >= 75
    assert report["product_specificity_score"] >= 75
    assert report["manual_review_notes"]


def test_implementation_plan_v2_has_states_and_acceptance(tmp_path):
    plan = write_implementation_plan(
        tmp_path,
        {
            "app": {"name": "Checklist"},
            "features": [{"title": "Add checklist item"}, {"title": "Mark done"}],
            "core_logic": {"persistence": "SharedPreferences"},
        },
    )

    assert plan["schema_version"] == 2
    assert plan["primary_user_flow"] == "Add checklist item"
    assert "empty" in plan["screen_states"]
    assert plan["acceptance_actions"]
    assert len(plan["core_features"]) <= 3


def test_scope_detection_ignores_negative_constraints():
    from craftsman.orchestrator.quality import _contains_positive_scope

    for text in (
        "No login, no account, without payment, and no backend.",
        "This app does not require login or subscription.",
        "无需登录、账号、支付或后端服务。",
        "避免订阅和云同步。",
        "An accountability timer with observer mode.",
    ):
        assert _contains_positive_scope(text) is False


def test_scope_detection_keeps_real_scope_as_advisory(tmp_path):
    workspace, project, metadata = _android_project(
        tmp_path,
        """
        package com.example
        fun MainActivity() {
            setContent {
                val value = rememberSaveable { mutableStateOf("Account") }
                TextField(value = value.value, onValueChange = { value.value = it })
                Button(onClick = { value.value = "Saved" }) { Text("Save account") }
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
        requirement={
            "app": {"name": "Account Notes"},
            "features": [{"title": "Account login"}],
        },
        icon_path=icon,
        screenshots=[str(shot)],
        metadata_root=metadata,
        verification="verified",
        device_acceptance_report=DEVICE_VERIFIED,
    )

    assert "scope_too_large" in report["failure_classes"]
    assert report["quality_score"] >= 75
    assert report["release_ready"] is True
    assert report["polish_required"] is False


def test_legacy_scope_only_quality_report_is_release_ready():
    from craftsman.orchestrator.quality import release_quality_gate

    decision = release_quality_gate({
        "quality_score": 94,
        "release_ready": False,
        "quality_report": {
            "quality_score": 94,
            "release_ready": False,
            "failure_classes": ["scope_too_large"],
        },
    })

    assert decision["passed"] is True
    assert decision["legacy_advisory_override"] is True
    assert decision["hard_failure_classes"] == []


def test_legacy_hard_failure_stays_blocked():
    from craftsman.orchestrator.quality import release_quality_gate

    decision = release_quality_gate({
        "quality_score": 94,
        "release_ready": False,
        "quality_report": {
            "quality_score": 94,
            "release_ready": False,
            "failure_classes": ["empty_ui"],
        },
    })

    assert decision["passed"] is False
    assert decision["hard_failure_classes"] == ["empty_ui"]

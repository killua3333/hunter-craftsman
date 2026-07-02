from pathlib import Path

from craftsman.orchestrator.verify_gates import run_verify_hard_gates


def test_verify_hard_gates_demo_mode_success(tmp_path):
    workspace = tmp_path / "workspace"
    project_dir = workspace / "project"
    project_dir.mkdir(parents=True)
    (workspace / "manifest.json").write_text("{}", encoding="utf-8")
    preview = workspace / "preview.html"
    preview.write_text("<html></html>", encoding="utf-8")
    demo_html = workspace / "demo.html"
    demo_html.write_text("<html></html>", encoding="utf-8")
    icon = workspace / "icon.png"
    icon.write_bytes(b"ok")
    shot = workspace / "shot.png"
    shot.write_bytes(b"ok")

    result = run_verify_hard_gates(
        backend_mode="demo",
        compile_exit_code=0,
        project_dir=project_dir,
        workspace=workspace,
        preview_html=str(preview),
        demo_html=demo_html,
        icon_path=icon,
        screenshots=[str(shot)],
    )
    assert result["ok"] is True


def test_verify_hard_gates_native_failure(tmp_path):
    workspace = tmp_path / "workspace"
    project_dir = workspace / "project"
    project_dir.mkdir(parents=True)
    demo_html = workspace / "demo.html"
    demo_html.write_text("<html></html>", encoding="utf-8")
    icon = workspace / "icon.png"
    icon.write_bytes(b"ok")

    result = run_verify_hard_gates(
        backend_mode="macos_xcode",
        compile_exit_code=1,
        project_dir=project_dir,
        workspace=workspace,
        preview_html=str(workspace / "preview.html"),
        demo_html=demo_html,
        icon_path=icon,
        screenshots=[],
    )
    assert result["ok"] is False
    assert "native compile gate failed" in result["failures"]


def test_verify_hard_gates_android_mode_success(tmp_path):
    workspace = tmp_path / "workspace"
    project_dir = workspace / "project"
    app_dir = project_dir / "app" / "src" / "main"
    app_dir.mkdir(parents=True)
    (project_dir / "app" / "build.gradle.kts").write_text("", encoding="utf-8")
    (app_dir / "AndroidManifest.xml").write_text("<manifest/>", encoding="utf-8")
    src_dir = app_dir / "java" / "com" / "craftsman"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "MainActivity.kt").write_text(
        "package com.craftsman\nfun MainActivity() { setContent { Button(onClick = {}) { remember { mutableStateOf(0) } } } }",
        encoding="utf-8",
    )
    preview = workspace / "preview.html"
    preview.write_text("<html></html>", encoding="utf-8")
    demo_html = workspace / "demo.html"
    demo_html.write_text("<html></html>", encoding="utf-8")
    icon = workspace / "icon.png"
    icon.write_bytes(b"ok")
    shot = workspace / "shot.png"
    shot.write_bytes(b"ok")

    result = run_verify_hard_gates(
        backend_mode="android_gradle",
        compile_exit_code=0,
        project_dir=project_dir,
        workspace=workspace,
        preview_html=str(preview),
        demo_html=demo_html,
        icon_path=icon,
        screenshots=[str(shot)],
    )
    assert result["ok"] is True


def test_verify_hard_gates_android_empty_ui_failure(tmp_path):
    workspace = tmp_path / "workspace"
    project_dir = workspace / "project"
    app_dir = project_dir / "app" / "src" / "main"
    src_dir = app_dir / "java" / "com" / "craftsman"
    src_dir.mkdir(parents=True)
    (project_dir / "app" / "build.gradle.kts").parent.mkdir(parents=True, exist_ok=True)
    (project_dir / "app" / "build.gradle.kts").write_text("", encoding="utf-8")
    (app_dir / "AndroidManifest.xml").write_text("<manifest/>", encoding="utf-8")
    (src_dir / "MainActivity.kt").write_text("package com.craftsman\nclass MainActivity", encoding="utf-8")
    demo_html = workspace / "demo.html"
    demo_html.parent.mkdir(parents=True, exist_ok=True)
    demo_html.write_text("<html></html>", encoding="utf-8")
    icon = workspace / "icon.png"
    icon.write_bytes(b"ok")

    result = run_verify_hard_gates(
        backend_mode="android_gradle",
        compile_exit_code=0,
        project_dir=project_dir,
        workspace=workspace,
        preview_html=str(workspace / "preview.html"),
        demo_html=demo_html,
        icon_path=icon,
        screenshots=[str(workspace / "shot.png")],
    )
    assert result["ok"] is False
    assert any("codegen_empty_ui" in item for item in result["failures"])

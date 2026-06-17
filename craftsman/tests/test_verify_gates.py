from pathlib import Path

from craftsman.orchestrator.verify_gates import run_verify_hard_gates


def test_verify_gates_emits_quality_signals(tmp_path):
    project_dir = tmp_path / "project"
    workspace = tmp_path / "workspace"
    project_dir.mkdir()
    workspace.mkdir()
    (project_dir / "app").mkdir(parents=True)
    (project_dir / "app" / "src" / "main").mkdir(parents=True)
    (project_dir / "app" / "src" / "main" / "AndroidManifest.xml").write_text("<manifest/>", encoding="utf-8")
    (project_dir / "app" / "build.gradle.kts").write_text("", encoding="utf-8")
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"icon")
    demo = tmp_path / "demo.html"
    demo.write_text("<html></html>", encoding="utf-8")

    result = run_verify_hard_gates(
        backend_mode="android_gradle",
        compile_exit_code=0,
        project_dir=project_dir,
        workspace=workspace,
        preview_html="preview.html",
        demo_html=demo,
        icon_path=icon,
        screenshots=["shot.png"],
    )
    assert result["ok"] is True
    assert "native_android_verification" in result["signals"]

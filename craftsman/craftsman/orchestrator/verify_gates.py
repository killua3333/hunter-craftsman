from __future__ import annotations

from pathlib import Path
from typing import Any


def run_verify_hard_gates(
    *,
    backend_mode: str,
    compile_exit_code: int,
    project_dir: Path,
    workspace: Path,
    preview_html: str,
    demo_html: Path,
    icon_path: Path,
    screenshots: list[str],
) -> dict[str, Any]:
    failures: list[str] = []
    suggested_rules: list[str] = []
    signals: list[str] = []

    if backend_mode == "macos_xcode":
        signals.append("native_ios_verification")
        if compile_exit_code != 0:
            failures.append("native compile gate failed")
            suggested_rules.append("修复编译错误后再进入打包阶段")
        if not list(project_dir.glob("*.xcodeproj")):
            failures.append("xcodeproj missing")
            suggested_rules.append("执行 xcodegen generate 生成工程文件")
        if not (workspace / "build.log").is_file():
            failures.append("build.log missing")
            suggested_rules.append("保留原生构建日志用于可追溯验证")
    elif backend_mode in {"android_gradle", "android_gradle_docker"}:
        signals.append("native_android_verification")
        if compile_exit_code != 0:
            failures.append("android compile gate failed")
            suggested_rules.append("修复 Gradle 构建错误后再进入打包阶段")
        if not (project_dir / "app" / "build.gradle.kts").is_file():
            failures.append("android app build script missing")
            suggested_rules.append("确保 app/build.gradle.kts 已生成")
        if not (project_dir / "app" / "src" / "main" / "AndroidManifest.xml").is_file():
            failures.append("android manifest missing")
            suggested_rules.append("确保 AndroidManifest.xml 存在")
    else:
        signals.append("demo_only_verification")
        if not Path(preview_html).is_file():
            failures.append("preview_html missing")
            suggested_rules.append("先生成 web demo 预览页")
        if not (workspace / "manifest.json").is_file():
            failures.append("manifest missing")
            suggested_rules.append("确保 scaffold 阶段输出 manifest.json")

    # Shared gates for both modes.
    if not icon_path.is_file():
        failures.append("icon artifact missing")
        suggested_rules.append("确保图标资源产出成功")
    if not screenshots:
        failures.append("screenshots missing")
        suggested_rules.append("至少生成一张截图用于发布素材验证")
    if not demo_html.is_file():
        failures.append("demo_html missing")
        suggested_rules.append("补齐 demo.html 产物")

    return {
        "ok": not failures,
        "failures": failures,
        "signals": signals,
        "suggested_rules": suggested_rules or ["检查 verify 阶段 hard gates 配置"],
    }

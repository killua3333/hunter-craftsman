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

    if backend_mode == "macos_xcode":
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
        if compile_exit_code != 0:
            failures.append("android compile gate failed")
            suggested_rules.append("修复 Gradle 构建错误后再进入打包阶段")
        if not (project_dir / "app" / "build.gradle.kts").is_file():
            failures.append("android app build script missing")
            suggested_rules.append("确保 app/build.gradle.kts 已生成")
        if not (project_dir / "app" / "src" / "main" / "AndroidManifest.xml").is_file():
            failures.append("android manifest missing")
            suggested_rules.append("确保 AndroidManifest.xml 存在")
        ui_failures, ui_rules = _check_android_ui_completeness(project_dir)
        failures.extend(ui_failures)
        suggested_rules.extend(ui_rules)
    else:
        if not Path(preview_html).is_file():
            failures.append("preview_html missing")
            suggested_rules.append("先生成 web demo 预览页")
        if not (workspace / "manifest.json").is_file():
            failures.append("manifest missing")
            suggested_rules.append("确保 scaffold 阶段输出 manifest.json")

    # Shared gates for both modes.
    # 图标和截图作为非阻断检查（LLM 生成可能因网络代理问题不稳定）
    warnings: list[str] = []
    icon_ok = icon_path.is_file()
    if not icon_ok:
        warnings.append("icon artifact missing (generation skipped, using placeholder)")
    if not screenshots:
        warnings.append("screenshots missing (generation skipped)")
    if not demo_html.is_file():
        failures.append("demo_html missing")
        suggested_rules.append("补齐 demo.html 产物")

    return {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "suggested_rules": suggested_rules or ["检查 verify 阶段 hard gates 配置"],
    }

def _check_android_ui_completeness(project_dir: Path) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    suggested_rules: list[str] = []
    src_root = project_dir / "app" / "src" / "main" / "java"
    candidates = list(src_root.rglob("MainActivity.kt")) if src_root.exists() else []
    if not candidates:
        return ["codegen_empty_ui: MainActivity.kt missing"], ["确保生成 Kotlin/Compose 主界面文件"]
    text = candidates[0].read_text(encoding="utf-8", errors="ignore")
    if "setContent" not in text:
        failures.append("codegen_empty_ui: main activity has no Compose content")
        suggested_rules.append("生成包含 setContent 和主屏内容的 Compose Activity")
    interactive_tokens = ("Button(", ".clickable", "TextField(", "OutlinedTextField(", "Checkbox(", "Switch(", "Slider(")
    if not any(token in text for token in interactive_tokens):
        failures.append("codegen_empty_ui: no interactive control found")
        suggested_rules.append("至少提供一个 Button/TextField/Checkbox/clickable 控件")
    state_tokens = ("remember", "mutableState", "SharedPreferences", "getSharedPreferences", "rememberSaveable")
    if not any(token in text for token in state_tokens):
        failures.append("codegen_empty_ui: no local state or persistence found")
        suggested_rules.append("使用 remember/mutableState 或 SharedPreferences 表达核心功能状态")
    return failures, suggested_rules

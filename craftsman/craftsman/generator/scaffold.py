from __future__ import annotations

import json
import logging
import platform
import re
import shutil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from craftsman.config import ROOT
from craftsman.llm import generate_code_llm
from craftsman.tools.shell import run_cmd

logger = logging.getLogger(__name__)

# LLM 返回时禁止覆盖的 Android 模板生成文件
# 保护 namespace = "com.craftsman" 固定，防止 LLM 违反 prompt 指令
_ANDROID_PROTECTED_PATHS = frozenset({
    "app/build.gradle.kts",
    "build.gradle.kts",
    "settings.gradle.kts",
    "app/src/main/AndroidManifest.xml",
})

_IOS_TEMPLATES = ROOT / "templates" / "ios-app"
_IOS_LOADER = Environment(
    loader=FileSystemLoader(str(_IOS_TEMPLATES)),
    autoescape=select_autoescape(enabled_extensions=()),
)
_ANDROID_TEMPLATES = ROOT / "templates" / "android-app"
_ANDROID_LOADER = Environment(
    loader=FileSystemLoader(str(_ANDROID_TEMPLATES)),
    autoescape=select_autoescape(enabled_extensions=()),
)


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", name)
    return cleaned[:32] or "CraftsmanApp"


def _feature_has_timer(features: list[Any]) -> bool:
    for feat in features:
        if not isinstance(feat, dict):
            continue
        ftype = str(feat.get("type") or "").lower()
        title = str(feat.get("title") or "")
        items_text = " ".join(str(i) for i in (feat.get("items") or []))
        blob = f"{title} {items_text}".lower()
        if ftype == "timer" or "计时" in blob or "番茄" in blob or "countdown" in blob:
            return True
    return False


def _platform_target(req: dict[str, Any]) -> str:
    platform_cfg = req.get("platform")
    if isinstance(platform_cfg, dict):
        target = str(platform_cfg.get("target") or "").strip().lower()
        if target in {"android", "ios"}:
            return target
    return "android"


def scaffold_project(workspace: Path, req: dict[str, Any]) -> Path:
    app = req["app"]
    app_name = _safe_name(app["name"])
    project_dir = workspace / "project"
    if project_dir.exists():
        shutil.rmtree(project_dir)
    platform_target = _platform_target(req)
    templates_root = _IOS_TEMPLATES if platform_target == "ios" else _ANDROID_TEMPLATES
    shutil.copytree(templates_root, project_dir, ignore=shutil.ignore_patterns("*.j2", "project.yml"))

    ctx = {
        "app_name": app_name,
        "display_name": app["name"],
        "bundle_id": app["bundle_id"],
        "version": app.get("version", "1.0.0"),
        "build": app.get("build", "1"),
        "min_ios": app.get("min_ios", "17.0"),
        "min_android_sdk": app.get("min_android_sdk", "24"),
        "application_id": app.get("application_id") or app.get("bundle_id"),
        "features": req.get("features") or [],
        "persistence": (req.get("core_logic") or {}).get("persistence", "none"),
        "primary_color": (req.get("branding") or {}).get("primary_color", "#007AFF"),
        "navigation": (req.get("ui_layout") or {}).get("navigation", "stack"),
        "has_timer": _feature_has_timer(req.get("features") or []),
    }

    sources = project_dir / "Sources"
    if platform_target == "ios":
        sources.mkdir(parents=True, exist_ok=True)
        llm_files = generate_code_llm(req, platform="ios")
        if llm_files:
            _write_codegen_files(project_dir, workspace, llm_files)
        else:
            for tpl_name in (
                "Sources/App.swift.j2",
                "Sources/ContentView.swift.j2",
                "Sources/Color+Hex.swift.j2",
            ):
                tpl = _IOS_LOADER.get_template(tpl_name)
                out_name = Path(tpl_name).name.replace(".j2", "")
                (sources / out_name).write_text(tpl.render(**ctx), encoding="utf-8")
            info_tpl = _IOS_LOADER.get_template("Info.plist.j2")
            (project_dir / "Info.plist").write_text(info_tpl.render(**ctx), encoding="utf-8")
            parts = app["bundle_id"].split(".")
            ctx["bundle_id_prefix"] = ".".join(parts[:-1]) if len(parts) > 1 else "com.craftsman"
            yml_tpl = _IOS_LOADER.get_template("project.yml.j2")
            (project_dir / "project.yml").write_text(yml_tpl.render(**ctx), encoding="utf-8")
    else:
        _render_android_templates(project_dir, ctx, include_main_activity=False)
        llm_files = _codegen_with_retry(req, platform="android", max_retries=3)
        if llm_files:
            _write_codegen_files(
                project_dir, workspace, llm_files,
                protected=_ANDROID_PROTECTED_PATHS,
            )
        else:
            raise RuntimeError(
                "Android codegen failed after retries: "
                "LLM did not return valid Kotlin/Compose source files. "
                "Check requirement.features completeness and retry with more detail."
            )

    manifest = {
        "app_name": app_name,
        "bundle_id": app["bundle_id"],
        "application_id": app.get("application_id") or app["bundle_id"],
        "scheme": app_name,
        "platform_target": platform_target,
    }
    (workspace / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    if platform_target == "ios":
        _maybe_run_xcodegen(project_dir)
    _write_store_metadata(project_dir, req, platform_target=platform_target)
    return project_dir


def _write_codegen_files(
    project_dir: Path,
    workspace: Path,
    llm_files: dict[str, str],
    *,
    protected: frozenset[str] = frozenset(),
) -> None:
    for rel, content in llm_files.items():
        if rel in ("index.html", "../index.html"):
            (workspace / "index.html").write_text(content, encoding="utf-8")
            continue
        if rel in protected:
            logger.warning("codegen returned protected file %s — skipped to preserve template", rel)
            continue
        target = project_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _codegen_with_retry(
    req: dict[str, Any],
    *,
    platform: str,
    max_retries: int = 3,
) -> dict[str, str] | None:
    """Call LLM codegen with retries, using increasingly specific error hints.

    - Attempt 1: standard codegen prompt
    - Attempt 2+: append hints about what went wrong (missing files, etc.)
    - Returns code files dict or None if all retries exhausted.
    """
    llm_files = generate_code_llm(req, platform=platform)
    if llm_files:
        return llm_files

    for attempt in range(2, max_retries + 1):
        logger.warning(
            "codegen attempt %d failed for platform=%s, retrying...",
            attempt - 1,
            platform,
        )
        # Retry with the same prompt — DeepSeek sometimes just needs a second try
        llm_files = generate_code_llm(req, platform=platform)
        if llm_files:
            logger.info("codegen succeeded on attempt %d", attempt)
            return llm_files

    logger.error("codegen exhausted %d retries for platform=%s", max_retries, platform)
    return None


def _render_android_templates(
    project_dir: Path,
    ctx: dict[str, Any],
    *,
    include_main_activity: bool = True,
) -> None:
    template_files = (
        "build.gradle.kts.j2",
        "settings.gradle.kts.j2",
        "gradle.properties.j2",
        "app/build.gradle.kts.j2",
        "app/src/main/AndroidManifest.xml.j2",
    )
    if include_main_activity:
        template_files = (*template_files, "app/src/main/java/com/craftsman/MainActivity.kt.j2")
    for tpl_name in template_files:
        tpl = _ANDROID_LOADER.get_template(tpl_name)
        out_name = tpl_name.replace(".j2", "")
        target = project_dir / out_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(tpl.render(**ctx), encoding="utf-8")


def _render_android_main_activity(project_dir: Path, ctx: dict[str, Any]) -> None:
    tpl = _ANDROID_LOADER.get_template("app/src/main/java/com/craftsman/MainActivity.kt.j2")
    target = project_dir / "app/src/main/java/com/craftsman/MainActivity.kt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(tpl.render(**ctx), encoding="utf-8")


def _maybe_run_xcodegen(project_dir: Path) -> None:
    if platform.system() != "Darwin":
        return
    if shutil.which("xcodegen") is None:
        return
    run_cmd(["xcodegen", "generate"], cwd=str(project_dir), timeout=120.0)


def _write_store_metadata(project_dir: Path, req: dict[str, Any], *, platform_target: str) -> None:
    store = req.get("store") or {}
    if platform_target == "ios":
        meta = project_dir / "fastlane" / "metadata" / "zh-Hans"
    else:
        meta = project_dir / "play" / "metadata" / "zh-CN"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "name.txt").write_text(req["app"]["name"], encoding="utf-8")
    (meta / "subtitle.txt").write_text(store.get("subtitle", ""), encoding="utf-8")
    (meta / "description.txt").write_text(store.get("description", ""), encoding="utf-8")
    keywords = store.get("keywords") or []
    (meta / "keywords.txt").write_text(",".join(keywords), encoding="utf-8")

from __future__ import annotations

import json
import platform
import re
import shutil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from craftsman.config import ROOT
from craftsman.llm import generate_code_llm
from craftsman.tools.shell import run_cmd

_TEMPLATES = ROOT / "templates" / "ios-app"
_LOADER = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(enabled_extensions=()),
)


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", name)
    return cleaned[:32] or "CraftsmanApp"


def scaffold_project(workspace: Path, req: dict[str, Any]) -> Path:
    app = req["app"]
    app_name = _safe_name(app["name"])
    project_dir = workspace / "project"
    if project_dir.exists():
        shutil.rmtree(project_dir)
    shutil.copytree(_TEMPLATES, project_dir, ignore=shutil.ignore_patterns("*.j2", "project.yml"))

    ctx = {
        "app_name": app_name,
        "display_name": app["name"],
        "bundle_id": app["bundle_id"],
        "version": app.get("version", "1.0.0"),
        "build": app.get("build", "1"),
        "min_ios": app.get("min_ios", "17.0"),
        "features": req.get("features") or [],
        "persistence": (req.get("core_logic") or {}).get("persistence", "none"),
        "primary_color": (req.get("branding") or {}).get("primary_color", "#007AFF"),
        "navigation": (req.get("ui_layout") or {}).get("navigation", "stack"),
    }

    sources = project_dir / "Sources"
    sources.mkdir(parents=True, exist_ok=True)
    llm_files = generate_code_llm(req)
    if llm_files:
        for rel, content in list(llm_files.items()):
            if rel in ("index.html", "../index.html"):
                (workspace / "index.html").write_text(content, encoding="utf-8")
                continue
            target = project_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    else:
        for tpl_name in (
            "Sources/App.swift.j2",
            "Sources/ContentView.swift.j2",
            "Sources/Color+Hex.swift.j2",
        ):
            tpl = _LOADER.get_template(tpl_name)
            out_name = Path(tpl_name).name.replace(".j2", "")
            (sources / out_name).write_text(tpl.render(**ctx), encoding="utf-8")

    info_tpl = _LOADER.get_template("Info.plist.j2")
    (project_dir / "Info.plist").write_text(info_tpl.render(**ctx), encoding="utf-8")

    parts = app["bundle_id"].split(".")
    ctx["bundle_id_prefix"] = ".".join(parts[:-1]) if len(parts) > 1 else "com.craftsman"
    yml_tpl = _LOADER.get_template("project.yml.j2")
    (project_dir / "project.yml").write_text(yml_tpl.render(**ctx), encoding="utf-8")

    manifest = {
        "app_name": app_name,
        "bundle_id": app["bundle_id"],
        "scheme": app_name,
    }
    (workspace / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    _maybe_run_xcodegen(project_dir)
    _write_fastlane_metadata(project_dir, req)
    return project_dir


def _maybe_run_xcodegen(project_dir: Path) -> None:
    if platform.system() != "Darwin":
        return
    if shutil.which("xcodegen") is None:
        return
    run_cmd(["xcodegen", "generate"], cwd=str(project_dir), timeout=120.0)


def _write_fastlane_metadata(project_dir: Path, req: dict[str, Any]) -> None:
    store = req.get("store") or {}
    meta = project_dir / "fastlane" / "metadata" / "zh-Hans"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "name.txt").write_text(req["app"]["name"], encoding="utf-8")
    (meta / "subtitle.txt").write_text(store.get("subtitle", ""), encoding="utf-8")
    (meta / "description.txt").write_text(store.get("description", ""), encoding="utf-8")
    keywords = store.get("keywords") or []
    (meta / "keywords.txt").write_text(",".join(keywords), encoding="utf-8")

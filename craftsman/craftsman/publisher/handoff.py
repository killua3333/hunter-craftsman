from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def platform_target(handoff: dict[str, Any]) -> str:
    platform = handoff.get("platform")
    if isinstance(platform, dict):
        target = str(platform.get("target") or "").strip().lower()
        if target in {"android", "ios"}:
            return target
    backend = str((handoff.get("build_provenance") or {}).get("backend") or "").lower()
    if "android" in backend:
        return "android"
    if "xcode" in backend or backend == "macos_xcode":
        return "ios"
    return "android"


def _uri_to_local_path(uri: str) -> Path | None:
    if not uri:
        return None
    if uri.startswith("file:"):
        parsed = urlparse(uri)
        return Path(unquote(parsed.path))
    if uri.startswith("object://local/runs/"):
        from craftsman.config import settings

        rel = uri.removeprefix("object://local/runs/")
        parts = rel.split("/", 1)
        if parts:
            run_id = parts[0]
            tail = parts[1] if len(parts) > 1 else ""
            base = settings.workspace_root / run_id
            return base / tail if tail else base
    if "://" not in uri:
        return Path(uri)
    return None


def resolve_project_dir(handoff: dict[str, Any]) -> Path | None:
    bundle = handoff.get("release_bundle") or {}
    project_uri = str(bundle.get("project_path") or "")
    local = _uri_to_local_path(project_uri)
    if local and local.is_dir():
        return local
    workspace_uri = str(handoff.get("workspace") or "")
    workspace = _uri_to_local_path(workspace_uri)
    if workspace and (workspace / "project").is_dir():
        return workspace / "project"
    run_id = str(handoff.get("run_id") or "")
    if run_id:
        from craftsman.config import settings

        candidate = settings.workspace_root / run_id / "project"
        if candidate.is_dir():
            return candidate
    return None


def resolve_workspace_dir(handoff: dict[str, Any]) -> Path | None:
    run_id = str(handoff.get("run_id") or "")
    if run_id:
        from craftsman.config import settings

        candidate = settings.workspace_root / run_id
        if candidate.is_dir():
            return candidate
    project = resolve_project_dir(handoff)
    if project is not None:
        return project.parent
    return None


def resolve_metadata_dir(handoff: dict[str, Any]) -> Path | None:
    bundle = handoff.get("release_bundle") or {}
    metadata_uri = str(bundle.get("metadata_path") or "")
    local = _uri_to_local_path(metadata_uri)
    if local and local.is_dir():
        return local
    project = resolve_project_dir(handoff)
    if project is None:
        return None
    for candidate in (project / "play" / "metadata" / "zh-CN", project / "fastlane" / "metadata" / "zh-Hans"):
        if candidate.is_dir():
            return candidate
    return None


def application_id(handoff: dict[str, Any]) -> str | None:
    app = handoff.get("app") if isinstance(handoff.get("app"), dict) else {}
    for value in (
        app.get("application_id"),
        app.get("bundle_id"),
        handoff.get("application_id"),
        handoff.get("bundle_id"),
    ):
        if value:
            return str(value)
    project = resolve_project_dir(handoff)
    if project is None:
        return None
    manifest = project.parent / "manifest.json"
    if manifest.is_file():
        import json

        data = json.loads(manifest.read_text(encoding="utf-8"))
        return data.get("application_id") or data.get("bundle_id")
    return None


def resolve_icon_path(handoff: dict[str, Any]) -> Path | None:
    bundle = handoff.get("release_bundle") or {}
    icon_uri = str(bundle.get("icon") or "")
    local = _uri_to_local_path(icon_uri)
    if local and local.is_file():
        return local
    workspace = resolve_workspace_dir(handoff)
    if workspace is not None:
        artifacts = workspace / "artifacts"
        for name in ("AppIcon.png", "icon.png", "ic_launcher_512x512.png"):
            candidate = artifacts / name
            if candidate.is_file():
                return candidate
        launchers = sorted(artifacts.glob("ic_launcher_*x*.png"), reverse=True) if artifacts.is_dir() else []
        for candidate in launchers:
            if candidate.is_file():
                return candidate
    return None


def resolve_screenshot_paths(handoff: dict[str, Any]) -> list[Path]:
    bundle = handoff.get("release_bundle") or {}
    shots: list[Path] = []
    for uri in bundle.get("screenshots") or []:
        local = _uri_to_local_path(str(uri))
        if local and local.is_file():
            shots.append(local)
    if shots:
        return shots
    workspace = resolve_workspace_dir(handoff)
    if workspace is None:
        return []
    artifacts = workspace / "artifacts"
    if not artifacts.is_dir():
        return []
    return sorted(p for p in artifacts.glob("screenshot*.png") if p.is_file())

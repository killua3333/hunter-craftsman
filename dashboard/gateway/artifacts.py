from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from craftsman_client import craftsman_request
from settings import settings


def _under_workspace(path: Path, workspace: Path) -> Path:
    resolved = path.resolve()
    root = workspace.resolve()
    if not str(resolved).startswith(str(root)):
        raise HTTPException(status_code=403, detail="path outside workspace")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return resolved


async def resolve_run_feedback(run_id: str) -> dict:
    row = await craftsman_request("GET", f"/v1/runs/{run_id}")
    feedback = row.get("feedback")
    if not isinstance(feedback, dict):
        raise HTTPException(status_code=409, detail="run not complete or no feedback yet")
    return feedback


def local_paths_from_feedback(feedback: dict) -> dict[str, str | list[str]]:
    artifacts = feedback.get("artifacts") if isinstance(feedback.get("artifacts"), dict) else {}
    local = artifacts.get("local_paths") if isinstance(artifacts.get("local_paths"), dict) else {}
    return local  # type: ignore[return-value]


async def artifact_file(run_id: str, relative: str) -> Path:
    feedback = await resolve_run_feedback(run_id)
    local = local_paths_from_feedback(feedback)
    workspace_raw = local.get("workspace")
    if workspace_raw:
        workspace = Path(str(workspace_raw))
    else:
        workspace = settings.workspace_root
    if relative == "preview.html":
        path_raw = local.get("preview_html")
        if not path_raw:
            raise HTTPException(status_code=404, detail="preview_html missing")
        return _under_workspace(Path(str(path_raw)), workspace)
    if relative == "demo.html":
        path_raw = local.get("demo_html")
        if not path_raw:
            raise HTTPException(status_code=404, detail="demo_html missing")
        return _under_workspace(Path(str(path_raw)), workspace)
    if relative == "icon.png" or relative.endswith("/AppIcon.png"):
        path_raw = local.get("icon")
        if not path_raw:
            raise HTTPException(status_code=404, detail="icon missing")
        return Path(str(path_raw)).resolve()
    if relative.startswith("screenshots/"):
        name = relative.split("/", 1)[1]
        shots = local.get("screenshots") or []
        for shot in shots:
            shot_path = Path(str(shot))
            if shot_path.name == name:
                return shot_path.resolve()
        raise HTTPException(status_code=404, detail="screenshot not found")
    return _under_workspace(workspace / relative, workspace)

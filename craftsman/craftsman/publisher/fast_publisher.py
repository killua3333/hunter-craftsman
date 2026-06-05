"""Fast-path publisher: skip LLM, build & upload directly.

Used by CLI `craftsman publish` and the web API.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from craftsman.config import settings

logger = logging.getLogger(__name__)

# A known-good template project (created by a prior Agent B run)
_FALLBACK_TEMPLATE = "1fb7d9e2-671e-4d84-9238-47c04c2b58d9"


def _workspace_run(run_id: str) -> Path:
    return settings.workspace_root / run_id


def _project_dir(run_id: str) -> Path:
    return _workspace_run(run_id) / "project"


def _artifacts_dir(run_id: str) -> Path:
    return _workspace_run(run_id) / "artifacts"


def _copy_template_project(run_id: str) -> Path:
    """Copy the template project into a new workspace directory."""
    template = settings.workspace_root / _FALLBACK_TEMPLATE / "project"
    if not template.is_dir():
        raise RuntimeError(f"template project not found: {template}")

    dest = _project_dir(run_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        template, dest,
        ignore=shutil.ignore_patterns(
            ".gradle", "keystore.properties", "release.keystore",
            "*.aab", "build", "app/build", "app/.gradle"
        ),
        dirs_exist_ok=True,
    )
    return dest


def write_minimal_main_activity(project_dir: Path, app_name: str = "Hello World") -> None:
    """Overwrite MainActivity.kt with a minimal Compose entry point."""
    kt_dir = project_dir / "app/src/main/java/com/craftsman"
    kt_dir.mkdir(parents=True, exist_ok=True)
    (kt_dir / "MainActivity.kt").write_text(f"""package com.craftsman

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {{
    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)
        setContent {{
            Surface(
                modifier = Modifier.fillMaxSize(),
                color = MaterialTheme.colorScheme.background
            ) {{
                Column(
                    modifier = Modifier.fillMaxSize(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {{
                    Text(
                        text = "{app_name}",
                        style = MaterialTheme.typography.headlineLarge
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = "Published automatically",
                        style = MaterialTheme.typography.bodyLarge
                    )
                }}
            }}
        }}
    }}
}}
""", encoding="utf-8")


def write_store_metadata(project_dir: Path, *, name: str, subtitle: str, description: str) -> None:
    """Populate Play Store listing metadata."""
    meta = project_dir / "play/metadata/zh-CN"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "name.txt").write_text(name, encoding="utf-8")
    (meta / "subtitle.txt").write_text(subtitle, encoding="utf-8")
    (meta / "description.txt").write_text(description, encoding="utf-8")
    (meta / "keywords.txt").write_text("auto,publish", encoding="utf-8")


def generate_assets(run_id: str) -> None:
    """Generate minimal icon and screenshot."""
    from PIL import Image, ImageDraw

    art = _artifacts_dir(run_id)
    art.mkdir(parents=True, exist_ok=True)
    ss_dir = art / "screenshots"
    ss_dir.mkdir(parents=True, exist_ok=True)

    icon = Image.new("RGBA", (512, 512), (76, 175, 80, 255))
    draw = ImageDraw.Draw(icon)
    draw.rectangle([100, 200, 412, 312], fill=(255, 255, 255, 255))
    draw.rectangle([230, 100, 282, 412], fill=(255, 255, 255, 255))
    icon.save(str(art / "AppIcon.png"))

    ss = Image.new("RGB", (1080, 1920), (76, 175, 80))
    ss.save(str(ss_dir / "screenshot_1.png"))


def write_manifest(run_id: str) -> None:
    """Write minimal manifest.json."""
    import json
    (_workspace_run(run_id) / "manifest.json").write_text(json.dumps({
        "app_name": "CraftsmanAuto",
        "bundle_id": settings.google_play_package_name or "com.craftsman.app",
        "application_id": settings.google_play_package_name or "com.craftsman.app",
        "scheme": "CraftsmanAuto",
        "platform_target": "android",
    }), encoding="utf-8")


def build_release_handoff(run_id: str) -> dict[str, Any]:
    """Build a release_handoff dict ready for /v1/releases/prepare."""
    pkg = settings.google_play_package_name or "com.craftsman.app"
    digest = hashlib.sha256(f"fast-{run_id}".encode()).hexdigest()
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "opportunity_id": str(uuid.uuid4()),
        "revision": 1,
        "platform": {"target": "android"},
        "requirement_digest": f"sha256:{digest}",
        "release_bundle": {
            "project_path": f"object://local/runs/{run_id}/project",
            "icon": f"object://local/runs/{run_id}/artifacts/AppIcon.png",
            "screenshots": [
                f"object://local/runs/{run_id}/artifacts/screenshots/screenshot_1.png"
            ],
            "metadata_path": f"object://local/runs/{run_id}/project/play/metadata",
        },
        "build_provenance": {
            "backend": "android_gradle",
            "backend_target": "fast-publish-cli",
            "craftsman_version": "0.1.0",
            "codegen_model": "handcrafted",
            "platform_note": "auto-published via craftsman publish",
            "verification": "fast",
        },
        "compliance_metadata": {
            "subtitle": "Auto Generated",
            "description": "Automatically published app from craftsman publish CLI.",
            "keywords": ["auto"],
            "privacy_url": "https://tempt-privacy.pages.dev/",
        },
        "agent_b_status": "implementation_complete",
        "workspace": f"object://local/runs/{run_id}",
        "release_id": run_id,
    }


def prepare_fast_project(
    app_name: str = "Hello World",
    subtitle: str = "Auto Published",
    description: str = "Automatically generated and published.",
) -> str:
    """Create a minimal project workspace and return run_id."""
    run_id = str(uuid.uuid4())
    logger.info("fast-publish: preparing project run_id=%s app_name=%r", run_id, app_name)

    project = _copy_template_project(run_id)
    write_minimal_main_activity(project, app_name)
    write_store_metadata(project, name=app_name, subtitle=subtitle, description=description)
    generate_assets(run_id)
    write_manifest(run_id)

    return run_id

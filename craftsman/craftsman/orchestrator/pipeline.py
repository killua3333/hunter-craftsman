from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from craftsman.callback import deliver_feedback
from craftsman.config import settings
from craftsman.feedback import build_feedback
from craftsman.gate import run_gate
from craftsman.generator.scaffold import scaffold_project
from craftsman.models import AgentBStatus, CraftsmanFeedback, RequirementPayload
from craftsman.orchestrator.reflexion import apply_fixes, save_build_log
from craftsman.schema_validate import validate_requirement
from craftsman.store.db import RunStore
from craftsman.tools import assets as assets_tool
from craftsman.tools import fastlane as fastlane_tool
from craftsman.tools import web_demo as web_demo_tool
from craftsman.tools import xcodebuild as xcode_tool
from craftsman.tools.xcode_errors import parse_xcode_errors

logger = logging.getLogger(__name__)


def _text_for_demo(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("description") or json.dumps(value, ensure_ascii=False)
    return ""


def analyze_requirement(raw: dict[str, Any]) -> CraftsmanFeedback:
    from craftsman.requirement_normalize import normalize_requirement

    raw = normalize_requirement(raw)
    schema_errors = validate_requirement(raw)
    try:
        req = RequirementPayload.model_validate(raw)
        payload = req.as_dict()
    except Exception as exc:
        return build_feedback(
            opportunity_id=raw.get("opportunity_id", "unknown"),
            revision=int(raw.get("revision") or 1),
            app_name=(raw.get("app") or {}).get("name", "Unknown"),
            accepted=False,
            status=AgentBStatus.NEEDS_CLARIFICATION,
            reasons=[f"payload: {exc}", *schema_errors],
            suggested_rules=["需求必须符合 requirement.v1.json"],
        )

    gate = run_gate(payload, schema_errors)
    status = AgentBStatus.ACCEPTED if gate.accepted else AgentBStatus.NEEDS_CLARIFICATION
    return build_feedback(
        opportunity_id=payload["opportunity_id"],
        revision=payload["revision"],
        app_name=payload["app"]["name"],
        accepted=gate.accepted,
        status=status,
        reasons=gate.reasons,
        suggested_rules=gate.suggested_rules,
        summary=gate.summary,
        estimated_complexity=gate.estimated_complexity,
        open_questions=gate.open_questions,
    )


def run_implementation(store: RunStore, run_id: str) -> CraftsmanFeedback:
    row = store.get_run(run_id)
    if not row:
        raise ValueError(f"run not found: {run_id}")

    from craftsman.requirement_normalize import normalize_requirement

    req = normalize_requirement(json.loads(row["requirement_json"]))
    opportunity_id = req["opportunity_id"]
    revision = req["revision"]
    app_name = req["app"]["name"]
    started = time.monotonic()
    deadline = started + settings.max_implementation_seconds

    workspace = settings.workspace_root / run_id
    workspace.mkdir(parents=True, exist_ok=True)
    store.update_run(run_id, status="in_progress", workspace_path=str(workspace))

    in_progress = build_feedback(
        opportunity_id=opportunity_id,
        revision=revision,
        app_name=app_name,
        accepted=True,
        status=AgentBStatus.IN_PROGRESS,
        run_id=run_id,
        summary="开始实现",
    )
    deliver_feedback(in_progress)
    store.update_run(run_id, status="in_progress", feedback=in_progress.to_agent_a_dict())

    can_build = xcode_tool.is_macos_with_xcode()
    build_skip_reason = ""
    if not can_build:
        build_skip_reason = (
            "当前主机不支持 xcodebuild，已切换为 Demo 产物模式；"
            f" {xcode_tool.platform_note()}"
        )

    try:
        project_dir = scaffold_project(workspace, req)
        preview_path = str(web_demo_tool.ensure_windows_demo(workspace, req))
        manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
        scheme = manifest["scheme"]
        xcodeproj = list(project_dir.glob("*.xcodeproj"))
        if can_build and not xcodeproj:
            fb = build_feedback(
                opportunity_id=opportunity_id,
                revision=revision,
                app_name=app_name,
                accepted=True,
                status=AgentBStatus.IMPLEMENTATION_FAILED,
                run_id=run_id,
                reasons=["未生成 .xcodeproj，请安装 xcodegen 并在 Mac 上重试"],
                suggested_rules=["在 Mac 上执行: brew install xcodegen && xcodegen generate"],
            )
            deliver_feedback(fb)
            store.update_run(run_id, status="failed", feedback=fb.to_agent_a_dict())
            return fb

        previous_fp: str | None = None
        last_errors: list[str] = []
        exit_code = 0
        log = ""
        if can_build:
            exit_code = 1
            for round_num in range(1, settings.max_reflexion_rounds + 1):
                if time.monotonic() > deadline:
                    last_errors.append(f"实际开发超过 {settings.max_implementation_seconds / 3600:.0f}h")
                    break
                exit_code, log = xcode_tool.simulator_build(project_dir, scheme)
                save_build_log(workspace, log)
                if exit_code == 0:
                    break
                parsed = parse_xcode_errors(log)
                last_errors = [e["message"] for e in parsed.get("errors") or []][:5]
                if not last_errors:
                    last_errors = [line for line in log.splitlines() if "error:" in line][-3:]
                changed, previous_fp = apply_fixes(
                    req, project_dir, parsed, round_num, previous_fp
                )
                if not changed:
                    break

            if exit_code != 0:
                fb = build_feedback(
                    opportunity_id=opportunity_id,
                    revision=revision,
                    app_name=app_name,
                    accepted=True,
                    status=AgentBStatus.IMPLEMENTATION_FAILED,
                    run_id=run_id,
                    reasons=last_errors or ["编译失败，详见 build.log"],
                    suggested_rules=["检查 Sources 语法", "确认 xcodegen 与模拟器名称配置"],
                    artifacts={"workspace": str(workspace), "build_log": str(workspace / "build.log")},
                )
                deliver_feedback(fb)
                store.update_run(run_id, status="failed", feedback=fb.to_agent_a_dict())
                return fb

        branding = req.get("branding") or {}
        store_meta = req.get("store") or {}
        artifacts_dir = workspace / "artifacts"
        icon_path = artifacts_dir / "AppIcon.png"
        assets_tool.generate_icon(
            icon_path,
            text=(branding.get("icon_text") or app_name[:1]),
            bg_hex=branding.get("primary_color", "#007AFF"),
        )
        shots = assets_tool.generate_screenshots(
            artifacts_dir / "screenshots",
            app_name=app_name,
            subtitle=store_meta.get("subtitle", app_name),
            bg_hex=branding.get("primary_color", "#007AFF"),
        )
        demo_html_path = artifacts_dir / "demo.html"
        web_demo_tool.write_artifacts_redirect(demo_html_path)

        fastlane_ok = False
        fastlane_log = "fastlane skipped (demo mode)"
        if can_build:
            fastlane_ok, fastlane_log = fastlane_tool.run_beta_lane(project_dir)
            (workspace / "fastlane.log").write_text(fastlane_log, encoding="utf-8")

        if can_build and fastlane_ok and "skipped" not in fastlane_log.lower():
            status = AgentBStatus.SUBMITTED
        else:
            status = AgentBStatus.READY_FOR_RELEASE

        reasons: list[str] = []
        if can_build:
            if not fastlane_ok:
                reasons.append("Fastlane 未完整执行，产物已生成")
        else:
            reasons.append(build_skip_reason)

        fb = build_feedback(
            opportunity_id=opportunity_id,
            revision=revision,
            app_name=app_name,
            accepted=True,
            status=status,
            run_id=run_id,
            reasons=reasons,
            summary="Demo 产物已生成" if not can_build else "编译成功",
            artifacts={
                "workspace": str(workspace),
                "icon": str(icon_path),
                "screenshots": shots,
                "project": str(project_dir),
                "preview_html": preview_path,
                "demo_html": str(demo_html_path),
            },
        )
        deliver_feedback(fb)
        store.update_run(run_id, status=status.value, feedback=fb.to_agent_a_dict())
        return fb

    except Exception as exc:
        logger.exception("implementation failed")
        fb = build_feedback(
            opportunity_id=opportunity_id,
            revision=revision,
            app_name=app_name,
            accepted=True,
            status=AgentBStatus.IMPLEMENTATION_FAILED,
            run_id=run_id,
            reasons=[str(exc)],
        )
        deliver_feedback(fb)
        store.update_run(
            run_id,
            status="failed",
            feedback=fb.to_agent_a_dict(),
            error_message=str(exc),
        )
        return fb

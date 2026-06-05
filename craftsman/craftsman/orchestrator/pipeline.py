from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from craftsman.callback import deliver_feedback
from craftsman.config import settings
from craftsman.feedback import build_feedback
from craftsman.gate import run_gate
from craftsman.generator.scaffold import scaffold_project
from craftsman.llm import reset_usage_events, usage_summary
from craftsman.models import AgentBStatus, CraftsmanFeedback, RequirementPayload
from craftsman.orchestrator.alerts import evaluate_run_alerts
from craftsman.orchestrator.failure_taxonomy import classify_build_failure, classify_runtime_exception
from craftsman.orchestrator.reflexion import apply_fixes, apply_gradle_fixes, save_build_log
from craftsman.orchestrator.verify_gates import run_verify_hard_gates
from craftsman.runtime import select_execution_backend
from craftsman.schema_validate import validate_requirement
from craftsman.store.db import RunStore
from craftsman.tools import assets as assets_tool
from craftsman.tools import web_demo as web_demo_tool
from craftsman.tools.gradle_errors import parse_gradle_errors
from craftsman.tools.xcode_errors import parse_xcode_errors

logger = logging.getLogger(__name__)

_ANDROID_BACKENDS = frozenset({"android_gradle", "android_gradle_docker"})


class WorkerStopRequested(Exception):
    """Background worker graceful shutdown — job should retry."""


def _text_for_demo(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("description") or json.dumps(value, ensure_ascii=False)
    return ""


def _phase_event(run_id: str, phase: str, detail: str) -> dict[str, Any]:
    return {"run_id": run_id, "phase": phase, "detail": detail}


def _record_phase(
    store: RunStore,
    run_id: str,
    phase_events: list[dict[str, Any]],
    *,
    phase: str,
    detail: str,
) -> None:
    phase_events.append(_phase_event(run_id, phase, detail))
    store.update_run(run_id, phase=phase, phase_detail=detail)
    store.append_event(run_id, phase, detail)


def _requirement_digest(req: dict[str, Any]) -> str:
    encoded = json.dumps(req, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _artifact_base_uri(run_id: str, workspace: Path) -> str:
    mode = settings.artifact_uri_mode.strip().lower()
    if mode == "file":
        return workspace.resolve().as_uri()
    prefix = settings.artifact_object_prefix.rstrip("/")
    return f"{prefix}/runs/{run_id}"


def _artifact_uri(path: Path, *, run_id: str, workspace: Path) -> str:
    mode = settings.artifact_uri_mode.strip().lower()
    if mode == "file":
        return path.resolve().as_uri()
    try:
        rel = path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        rel = path.name
    return f"{_artifact_base_uri(run_id, workspace)}/{rel}"


def _platform_target(req: dict[str, Any]) -> str:
    platform = req.get("platform")
    if isinstance(platform, dict):
        target = str(platform.get("target") or "").strip().lower()
        if target in {"android", "ios"}:
            return target
    return "android"


def _build_release_handoff(
    *,
    run_id: str,
    req: dict[str, Any],
    workspace: Path,
    project_dir: Path,
    artifacts: dict[str, Any],
    backend_mode: str,
    backend_target: str,
    platform_note: str,
    verification: str = "demo",
) -> dict[str, Any]:
    platform_target = _platform_target(req)
    release_bundle: dict[str, Any] = {
        "project_path": str(artifacts.get("project")),
        "icon": artifacts.get("icon"),
        "screenshots": artifacts.get("screenshots") or [],
        "metadata_path": str(artifacts.get("metadata_path")),
    }
    if artifacts.get("aab"):
        release_bundle["aab_path"] = str(artifacts.get("aab"))
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "opportunity_id": req["opportunity_id"],
        "revision": req["revision"],
        "platform": {"target": platform_target},
        "requirement_digest": _requirement_digest(req),
        "release_bundle": release_bundle,
        "build_provenance": {
            "backend": backend_mode,
            "backend_target": backend_target,
            "craftsman_version": "0.1.0",
            "codegen_model": settings.deepseek_pro_model,
            "platform_note": platform_note,
            "verification": verification,
        },
        "compliance_metadata": {
            "subtitle": ((req.get("store") or {}).get("subtitle") or ""),
            "description": ((req.get("store") or {}).get("description") or ""),
            "keywords": list((req.get("store") or {}).get("keywords") or []),
            "privacy_url": ((req.get("store") or {}).get("privacy_url") or ""),
        },
        "agent_b_status": AgentBStatus.IMPLEMENTATION_COMPLETE.value,
        "workspace": str(artifacts.get("workspace")),
    }


def analyze_requirement(raw: dict[str, Any]) -> CraftsmanFeedback:
    from craftsman.requirement_normalize import normalize_requirement, soft_fill_requirement

    raw = normalize_requirement(raw)
    if settings.gate_mode.strip().lower() == "soft":
        raw = soft_fill_requirement(raw)
    schema_errors = validate_requirement(raw)
    try:
        req = RequirementPayload.model_validate(raw)
        payload = req.as_dict()
    except Exception as exc:
        if settings.gate_mode.strip().lower() == "soft" and settings.gate_auto_accept:
            raw = soft_fill_requirement(raw)
            try:
                req = RequirementPayload.model_validate(raw)
                payload = req.as_dict()
            except Exception:
                return build_feedback(
                    opportunity_id=raw.get("opportunity_id", "unknown"),
                    revision=int(raw.get("revision") or 1),
                    app_name=(raw.get("app") or {}).get("name", "Unknown"),
                    accepted=False,
                    status=AgentBStatus.NEEDS_CLARIFICATION,
                    reasons=[f"payload: {exc}", *schema_errors],
                    suggested_rules=["需求必须符合 requirement.v1.json"],
                )
        else:
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


def _maybe_scope_retry(
    store: RunStore,
    run_id: str,
    fb: CraftsmanFeedback,
    req: dict[str, Any],
    scope_retry_depth: int,
) -> CraftsmanFeedback:
    if (
        fb.agent_b_status != AgentBStatus.IMPLEMENTATION_FAILED
        or scope_retry_depth > 0
        or req.get("_scope_retry")
    ):
        return fb
    from craftsman.requirement_normalize import shrink_requirement_scope

    shrunk = shrink_requirement_scope(req)
    store.update_run(
        run_id,
        requirement_json=json.dumps(shrunk, ensure_ascii=False),
        status="queued",
        error_message=None,
    )
    return run_implementation(store, run_id, scope_retry_depth=scope_retry_depth + 1)


def run_implementation(
    store: RunStore,
    run_id: str,
    *,
    scope_retry_depth: int = 0,
    should_stop: Callable[[], bool] | None = None,
) -> CraftsmanFeedback:
    row = store.get_run(run_id)
    if not row:
        raise ValueError(f"run not found: {run_id}")

    from craftsman.requirement_normalize import normalize_requirement, shrink_requirement_scope

    req = normalize_requirement(json.loads(row["requirement_json"]))
    platform_target = _platform_target(req)
    opportunity_id = req["opportunity_id"]
    revision = req["revision"]
    app_name = req["app"]["name"]
    started = time.monotonic()
    deadline = started + settings.max_implementation_seconds
    reset_usage_events()
    phase_durations: dict[str, float] = {}
    last_phase: str | None = None
    last_phase_tick = started

    def emit_alerts(status: str, failure_class: str | None, total_duration_seconds: float) -> list[dict[str, Any]]:
        alerts = evaluate_run_alerts(
            run_id=run_id,
            opportunity_id=opportunity_id,
            revision=revision,
            status=status,
            total_duration_seconds=total_duration_seconds,
            failure_class=failure_class,
        )
        for alert in alerts:
            logger.warning("run_alert=%s", json.dumps(alert, ensure_ascii=False))
        return alerts

    def enter_phase(phase: str, detail: str) -> None:
        nonlocal last_phase, last_phase_tick
        if should_stop and should_stop():
            raise WorkerStopRequested("worker shutdown requested")
        now = time.monotonic()
        if last_phase is not None:
            phase_durations[last_phase] = round(now - last_phase_tick, 4)
        last_phase = phase
        last_phase_tick = now
        _record_phase(store, run_id, phase_events, phase=phase, detail=detail)

    workspace = settings.workspace_root / run_id
    workspace.mkdir(parents=True, exist_ok=True)
    store.update_run(run_id, status="in_progress", workspace_path=str(workspace))
    phase_events: list[dict[str, Any]] = []
    enter_phase("spec_normalize", "normalized requirement")

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

    backend = select_execution_backend(req)
    can_build = backend.can_compile()
    build_skip_reason = ""
    if not can_build:
        build_skip_reason = f"当前执行后端不支持构建验证，已跳过编译阶段； {backend.platform_note()}"

    try:
        free_bytes = shutil.disk_usage(settings.workspace_root).free
        if free_bytes < settings.min_free_disk_bytes:
            raise RuntimeError(
                f"磁盘空间不足：可用 {free_bytes // (1024 ** 3)} GB，"
                f"需要至少 {settings.min_free_disk_bytes // (1024 ** 3)} GB"
            )
        enter_phase("plan", "scaffold project and derive scheme")
        if time.monotonic() > deadline:
            raise TimeoutError(f"实现超时（>{settings.max_implementation_seconds}s）")
        project_dir = scaffold_project(workspace, req)
        enter_phase("codegen", "project scaffold/codegen complete")
        preview_path = str(web_demo_tool.ensure_windows_demo(workspace, req))
        manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
        scheme = manifest["scheme"]
        xcodeproj = list(project_dir.glob("*.xcodeproj"))
        if backend.mode == "macos_xcode" and can_build and not xcodeproj:
            taxonomy = classify_build_failure(
                ["xcodeproj missing", "xcodegen generate not executed"],
            )
            fb = build_feedback(
                opportunity_id=opportunity_id,
                revision=revision,
                app_name=app_name,
                accepted=True,
                status=AgentBStatus.IMPLEMENTATION_FAILED,
                run_id=run_id,
                reasons=["未生成 .xcodeproj，请安装 xcodegen 并在 Mac 上重试", taxonomy["category"]],
                suggested_rules=[
                    "在 Mac 上执行: brew install xcodegen && xcodegen generate",
                    *taxonomy["suggested_rules"],
                ],
            )
            deliver_feedback(fb)
            store.update_run(run_id, status="failed", feedback=fb.to_agent_a_dict())
            return _maybe_scope_retry(store, run_id, fb, req, scope_retry_depth)

        previous_fp: str | None = None
        last_errors: list[str] = []
        exit_code = 0
        log = ""
        smoke_skip_reason = ""
        privacy_note = ""
        enter_phase("verify", "start verification")
        if backend.mode == "macos_xcode" and can_build:
            exit_code = 1
            for round_num in range(1, settings.max_reflexion_rounds + 1):
                if time.monotonic() > deadline:
                    last_errors.append(f"实际开发超过 {settings.max_implementation_seconds / 3600:.0f}h")
                    break
                result = backend.compile(project_dir, scheme)
                exit_code = result.exit_code
                log = result.log
                save_build_log(workspace, log, backend="macos_xcode")
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
                taxonomy = classify_build_failure(last_errors, log)
                fb = build_feedback(
                    opportunity_id=opportunity_id,
                    revision=revision,
                    app_name=app_name,
                    accepted=True,
                    status=AgentBStatus.IMPLEMENTATION_FAILED,
                    run_id=run_id,
                    reasons=(last_errors or ["编译失败，详见 build.log"]) + [taxonomy["category"]],
                    suggested_rules=taxonomy["suggested_rules"],
                    artifacts={
                        "workspace": _artifact_base_uri(run_id, workspace),
                        "build_log": _artifact_uri(workspace / "build.log", run_id=run_id, workspace=workspace),
                        "local_paths": {
                            "workspace": str(workspace),
                            "build_log": str(workspace / "build.log"),
                        },
                        "failure_taxonomy": taxonomy,
                    },
                )
                deliver_feedback(fb)
                store.update_run(run_id, status="failed", feedback=fb.to_agent_a_dict())
                return _maybe_scope_retry(store, run_id, fb, req, scope_retry_depth)
        elif can_build and backend.mode in _ANDROID_BACKENDS:
            exit_code = 1
            max_rounds = min(settings.max_reflexion_rounds, 2)
            log_backend = backend.mode
            for round_num in range(1, max_rounds + 1):
                if time.monotonic() > deadline:
                    last_errors.append(f"实际开发超过 {settings.max_implementation_seconds / 3600:.0f}h")
                    break
                result = backend.compile(project_dir, scheme)
                exit_code = result.exit_code
                log = result.log
                save_build_log(workspace, log, backend=log_backend)
                if exit_code == 0:
                    break
                parsed = parse_gradle_errors(log)
                last_errors = [e["message"] for e in parsed.get("errors") or []][:5]
                if not last_errors:
                    last_errors = result.reasons or [
                        line for line in log.splitlines() if "error" in line.lower()
                    ][-3:]
                changed, previous_fp = apply_gradle_fixes(
                    req, project_dir, parsed, round_num, previous_fp
                )
                if not changed:
                    break

            if exit_code != 0:
                taxonomy = classify_build_failure(last_errors, log)
                fb = build_feedback(
                    opportunity_id=opportunity_id,
                    revision=revision,
                    app_name=app_name,
                    accepted=True,
                    status=AgentBStatus.IMPLEMENTATION_FAILED,
                    run_id=run_id,
                    reasons=(last_errors or ["Gradle 构建失败，详见 build.log"]) + [taxonomy["category"]],
                    suggested_rules=taxonomy["suggested_rules"],
                    artifacts={
                        "workspace": _artifact_base_uri(run_id, workspace),
                        "build_log": _artifact_uri(workspace / "build.log", run_id=run_id, workspace=workspace),
                        "local_paths": {
                            "workspace": str(workspace),
                            "build_log": str(workspace / "build.log"),
                        },
                        "failure_taxonomy": taxonomy,
                    },
                )
                deliver_feedback(fb)
                store.update_run(run_id, status="failed", feedback=fb.to_agent_a_dict())
                return _maybe_scope_retry(store, run_id, fb, req, scope_retry_depth)

            from craftsman.tools.android_smoke import parse_smoke_crash, run_android_smoke

            manifest_data = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            package_id = str(
                manifest_data.get("application_id")
                or manifest_data.get("bundle_id")
                or (req.get("app") or {}).get("bundle_id")
                or ""
            )
            smoke_ok = True
            for smoke_round in range(1, settings.android_smoke_max_rounds + 1):
                smoke = run_android_smoke(project_dir, package_id)
                (workspace / "smoke.log").write_text(smoke.log, encoding="utf-8")
                if smoke.skipped:
                    smoke_skip_reason = smoke.reason
                    break
                if smoke.ok:
                    smoke_ok = True
                    break
                smoke_ok = False
                parsed_smoke = parse_smoke_crash(smoke.log)
                changed, previous_fp = apply_gradle_fixes(
                    req, project_dir, parsed_smoke, smoke_round, previous_fp
                )
                if not changed:
                    break
                result = backend.compile(project_dir, scheme)
                exit_code = result.exit_code
                log = result.log
                save_build_log(workspace, log, backend=log_backend)
                if exit_code != 0:
                    last_errors = result.reasons or ["recompile after smoke fix failed"]
                    break

            if not smoke_ok and not smoke_skip_reason:
                taxonomy = classify_build_failure(["smoke test crash"], smoke.log)
                fb = build_feedback(
                    opportunity_id=opportunity_id,
                    revision=revision,
                    app_name=app_name,
                    accepted=True,
                    status=AgentBStatus.IMPLEMENTATION_FAILED,
                    run_id=run_id,
                    reasons=["冒烟测试崩溃，详见 smoke.log", taxonomy["category"]],
                    suggested_rules=taxonomy["suggested_rules"],
                    artifacts={
                        "workspace": _artifact_base_uri(run_id, workspace),
                        "local_paths": {
                            "workspace": str(workspace),
                            "smoke_log": str(workspace / "smoke.log"),
                        },
                        "failure_taxonomy": taxonomy,
                    },
                )
                deliver_feedback(fb)
                store.update_run(run_id, status="failed", feedback=fb.to_agent_a_dict())
                return _maybe_scope_retry(store, run_id, fb, req, scope_retry_depth)

            if exit_code != 0:
                taxonomy = classify_build_failure(
                    last_errors or ["recompile after smoke fix failed"],
                    log,
                )
                fb = build_feedback(
                    opportunity_id=opportunity_id,
                    revision=revision,
                    app_name=app_name,
                    accepted=True,
                    status=AgentBStatus.IMPLEMENTATION_FAILED,
                    run_id=run_id,
                    reasons=(last_errors or ["冒烟修复后编译失败"]) + [taxonomy["category"]],
                    suggested_rules=taxonomy["suggested_rules"],
                    artifacts={
                        "workspace": _artifact_base_uri(run_id, workspace),
                        "build_log": _artifact_uri(workspace / "build.log", run_id=run_id, workspace=workspace),
                        "local_paths": {
                            "workspace": str(workspace),
                            "build_log": str(workspace / "build.log"),
                            "smoke_log": str(workspace / "smoke.log"),
                        },
                        "failure_taxonomy": taxonomy,
                    },
                )
                deliver_feedback(fb)
                store.update_run(run_id, status="failed", feedback=fb.to_agent_a_dict())
                return _maybe_scope_retry(store, run_id, fb, req, scope_retry_depth)

        elif can_build:
            result = backend.compile(project_dir, scheme)
            exit_code = result.exit_code
            log = result.log
            save_build_log(workspace, log, backend=backend.mode)
            if not result.ok:
                taxonomy = classify_build_failure(
                    result.reasons or ["构建失败，详见 build.log"],
                    log,
                )
                fb = build_feedback(
                    opportunity_id=opportunity_id,
                    revision=revision,
                    app_name=app_name,
                    accepted=True,
                    status=AgentBStatus.IMPLEMENTATION_FAILED,
                    run_id=run_id,
                    reasons=(result.reasons or ["构建失败，详见 build.log"]) + [taxonomy["category"]],
                    suggested_rules=taxonomy["suggested_rules"],
                    artifacts={
                        "workspace": _artifact_base_uri(run_id, workspace),
                        "build_log": _artifact_uri(workspace / "build.log", run_id=run_id, workspace=workspace),
                        "local_paths": {
                            "workspace": str(workspace),
                            "build_log": str(workspace / "build.log"),
                        },
                        "failure_taxonomy": taxonomy,
                    },
                )
                deliver_feedback(fb)
                store.update_run(run_id, status="failed", feedback=fb.to_agent_a_dict())
                return _maybe_scope_retry(store, run_id, fb, req, scope_retry_depth)

        if _platform_target(req) == "android":
            from craftsman.publisher.privacy_policy import ensure_privacy_url

            privacy_result = ensure_privacy_url(req, workspace)
            if privacy_result.get("skipped"):
                pass
            elif not privacy_result.get("ok"):
                privacy_note = f"privacy_deploy_failed: {privacy_result.get('message', 'unknown')}"
            store.update_run(
                run_id,
                requirement_json=json.dumps(req, ensure_ascii=False),
            )

        verification = "verified" if can_build and exit_code == 0 else "demo"
        enter_phase("package", "collect implementation artifacts")
        branding = req.get("branding") or {}
        store_meta = req.get("store") or {}
        features_list = req.get("features") or []

        # B3: 按品类自动选择色板
        palette = assets_tool.choose_palette(app_name, [f.get("title", "") if isinstance(f, dict) else str(f) for f in features_list])

        # 如果没有 LLM 指定的 primary_color，使用色板的
        primary_color = branding.get("primary_color") or palette["primary"]
        if not branding.get("primary_color"):
            branding["primary_color"] = primary_color

        artifacts_dir = workspace / "artifacts"
        icon_path = artifacts_dir / "AppIcon.png"

        # B1: 优先 LLM 生成 SVG 图标
        feature_titles = [f.get("title", "") if isinstance(f, dict) else str(f) for f in features_list][:5]
        icon_paths = assets_tool.generate_icon_via_llm(
            icon_path,
            app_name=app_name,
            branding_text=branding.get("icon_text") or "",
            features=feature_titles,
            palette=palette,
        )

        # B4: 截图中增强 benefit_text
        benefit_text = store_meta.get("benefit", "")
        if not benefit_text and features_list:
            # 从功能列表自动生成 benefit 文案
            feature_names = [f.get("title", "") if isinstance(f, dict) else str(f) for f in features_list[:3]]
            if feature_names:
                benefit_text = " • ".join(fn for fn in feature_names if fn)
                if len(benefit_text) > 80:
                    benefit_text = benefit_text[:77] + "..."

        shots = assets_tool.generate_screenshots(
            artifacts_dir / "screenshots",
            app_name=app_name,
            subtitle=store_meta.get("subtitle", app_name),
            bg_hex=primary_color,
            benefit_text=benefit_text,
            palette=palette,
            features=features_list if features_list else None,
        )
        demo_html_path = artifacts_dir / "demo.html"
        web_demo_tool.write_artifacts_redirect(demo_html_path)
        gate_result = run_verify_hard_gates(
            backend_mode=backend.mode,
            compile_exit_code=exit_code,
            project_dir=project_dir,
            workspace=workspace,
            preview_html=preview_path,
            demo_html=demo_html_path,
            icon_path=icon_path,
            screenshots=shots,
        )
        if not gate_result["ok"]:
            fb = build_feedback(
                opportunity_id=opportunity_id,
                revision=revision,
                app_name=app_name,
                accepted=True,
                status=AgentBStatus.IMPLEMENTATION_FAILED,
                run_id=run_id,
                reasons=["verify_hard_gate_failed", *gate_result["failures"]],
                suggested_rules=gate_result["suggested_rules"],
                artifacts={
                    "workspace": _artifact_base_uri(run_id, workspace),
                    "local_paths": {"workspace": str(workspace)},
                    "verify_hard_gates": gate_result,
                },
            )
            deliver_feedback(fb)
            store.update_run(run_id, status="failed", feedback=fb.to_agent_a_dict())
            return _maybe_scope_retry(store, run_id, fb, req, scope_retry_depth)

        status = AgentBStatus.IMPLEMENTATION_COMPLETE

        reasons: list[str] = []
        if verification == "demo":
            reasons.append(build_skip_reason or "demo-only：已跳过原生编译验证")
        else:
            reasons.append("实现与验证完成，发布步骤由 Agent C 负责")
        if smoke_skip_reason:
            reasons.append(smoke_skip_reason)
        if privacy_note:
            reasons.append(privacy_note)

        workspace_uri = _artifact_base_uri(run_id, workspace)
        project_uri = _artifact_uri(project_dir, run_id=run_id, workspace=workspace)
        preview_uri = _artifact_uri(Path(preview_path), run_id=run_id, workspace=workspace)
        demo_html_uri = _artifact_uri(demo_html_path, run_id=run_id, workspace=workspace)
        icon_uri = _artifact_uri(icon_path, run_id=run_id, workspace=workspace)
        screenshots_uri = [_artifact_uri(Path(s), run_id=run_id, workspace=workspace) for s in shots]
        metadata_root = (
            project_dir / "fastlane" / "metadata"
            if backend.mode == "macos_xcode"
            else (project_dir / "play" / "metadata")
        )
        metadata_uri = _artifact_uri(metadata_root, run_id=run_id, workspace=workspace)
        artifacts_payload = {
            "workspace": workspace_uri,
            "icon": icon_uri,
            "screenshots": screenshots_uri,
            "project": project_uri,
            "metadata_path": metadata_uri,
            "preview_html": preview_uri,
            "demo_html": demo_html_uri,
            "phase_events": phase_events,
            "storage": {
                "mode": settings.artifact_uri_mode,
                "base_uri": workspace_uri,
            },
            "local_paths": {
                "workspace": str(workspace),
                "icon": str(icon_path),
                "screenshots": shots,
                "project": str(project_dir),
                "metadata_path": str(metadata_root),
                "preview_html": preview_path,
                "demo_html": str(demo_html_path),
            },
        }
        enter_phase("complete", "implementation complete and handoff generated")
        phase_durations["complete"] = round(time.monotonic() - last_phase_tick, 4)
        total_duration = round(time.monotonic() - started, 4)
        alerts = emit_alerts(status.value, None, total_duration)
        metrics_payload = {
            "phase_durations_seconds": phase_durations,
            "total_duration_seconds": total_duration,
            "failure_class": None,
            "llm_usage": usage_summary(),
            "alerts": alerts,
        }
        artifacts_payload["metrics"] = metrics_payload
        artifacts_payload["verification"] = verification
        release_handoff = _build_release_handoff(
            run_id=run_id,
            req=req,
            workspace=workspace,
            project_dir=project_dir,
            artifacts=artifacts_payload,
            backend_mode=backend.mode,
            backend_target=str(getattr(backend, "target", "unknown")),
            platform_note=backend.platform_note(),
            verification=verification,
        )
        artifacts_payload["release_handoff"] = release_handoff

        fb = build_feedback(
            opportunity_id=opportunity_id,
            revision=revision,
            app_name=app_name,
            accepted=True,
            status=status,
            run_id=run_id,
            reasons=reasons or ["实现完成"],
            summary="实现与验证完成（可交接发布）",
            artifacts=artifacts_payload,
            release_handoff=release_handoff,
            verification=verification,
        )
        deliver_feedback(fb)
        store.update_run(
            run_id,
            status=status.value,
            feedback=fb.to_agent_a_dict(),
        )
        logger.info(
            "run_metrics=%s",
            json.dumps(
                {
                    "run_id": run_id,
                    "opportunity_id": opportunity_id,
                    "revision": revision,
                    "status": status.value,
                    **metrics_payload,
                },
                ensure_ascii=False,
            ),
        )
        return fb

    except WorkerStopRequested:
        raise
    except Exception as exc:
        logger.exception("implementation failed")
        enter_phase("failed", "implementation failed")
        phase_durations["failed"] = round(time.monotonic() - last_phase_tick, 4)
        runtime_taxonomy = classify_runtime_exception(exc)
        failure_class = runtime_taxonomy["category"]
        total_duration = round(time.monotonic() - started, 4)
        alerts = emit_alerts("failed", failure_class, total_duration)
        fb = build_feedback(
            opportunity_id=opportunity_id,
            revision=revision,
            app_name=app_name,
            accepted=True,
            status=AgentBStatus.IMPLEMENTATION_FAILED,
            run_id=run_id,
            reasons=[str(exc), runtime_taxonomy["category"]],
            suggested_rules=["检查依赖与环境状态后重试"],
            artifacts={"failure_taxonomy": runtime_taxonomy},
        )
        deliver_feedback(fb)
        store.update_run(
            run_id,
            status="failed",
            feedback=fb.to_agent_a_dict(),
            error_message=str(exc),
        )
        logger.info(
            "run_metrics=%s",
            json.dumps(
                {
                    "run_id": run_id,
                    "opportunity_id": opportunity_id,
                    "revision": revision,
                    "status": "failed",
                    "phase_durations_seconds": phase_durations,
                    "total_duration_seconds": total_duration,
                    "failure_class": failure_class,
                    "llm_usage": usage_summary(),
                    "alerts": alerts,
                },
                ensure_ascii=False,
            ),
        )
        return _maybe_scope_retry(store, run_id, fb, req, scope_retry_depth)

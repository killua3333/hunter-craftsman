"""Hunter (Agent A) 与 Craftsman (Agent B) 的最小联通桥接。"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from hunter.schemas import AppOpportunityBlueprint


class CraftsmanHTTPError(RuntimeError):
    def __init__(self, message: str, *, code: str, status_code: int, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


def _requested_contract_version() -> str:
    return os.getenv("CRAFTSMAN_CONTRACT_VERSION", "1.0").strip() or "1.0"


def _ensure_contract_compatibility(payload: dict[str, Any]) -> None:
    response_version = payload.get("contract_version")
    if response_version is None:
        return
    requested = _requested_contract_version()
    if str(response_version) != requested:
        raise RuntimeError(
            f"contract version mismatch: requested={requested} response={response_version}"
        )


def _is_retryable_runtime_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "unreachable",
            "timeout",
            "timed out",
            "connection reset",
            "connection aborted",
            "temporarily unavailable",
            "connection refused",
        )
    )


def _with_retry(fn: Callable[[], dict[str, Any]], *, attempts: int = 2) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except CraftsmanHTTPError as exc:
            last_exc = exc
            if not exc.retryable or exc.status_code < 500 or attempt >= attempts:
                raise
        except RuntimeError as exc:
            last_exc = exc
            if (not _is_retryable_runtime_error(exc)) or attempt >= attempts:
                raise
        import time

        time.sleep(min(0.25 * attempt, 1.0))
    assert last_exc is not None
    raise last_exc


def craftsman_analyze_timeout_seconds() -> float:
    raw = os.getenv("CRAFTSMAN_ANALYZE_TIMEOUT_SECONDS", "90")
    try:
        return float(raw)
    except ValueError:
        return 90.0


def _safe_token(value: str, *, fallback: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    if token:
        return token[:24]
    return fallback


def _platform_target(requirement: dict[str, Any]) -> str:
    platform = requirement.get("platform")
    if isinstance(platform, dict):
        target = str(platform.get("target") or "").strip().lower()
        if target in {"android", "ios"}:
            return target
    return "android"


def build_requirement_from_blueprint(
    blueprint: AppOpportunityBlueprint,
    *,
    opportunity_id: str | None = None,
    revision: int = 1,
) -> dict[str, Any]:
    """
    将 Agent A 输出映射为 Craftsman requirement.v1 输入。

    优先使用 blueprint.requirement；缺失时回退到启发式填充（兼容旧输出）。
    """
    if not blueprint.accepted:
        reason = blueprint.rejection_reason or "机会未通过护栏"
        raise ValueError(f"blueprint rejected: {reason}")

    app_token = _safe_token(blueprint.app_name, fallback="demo-app")
    oid = opportunity_id or f"{app_token}-{datetime.now(timezone.utc).strftime('%m%d%H%M')}"

    if blueprint.requirement is not None:
        body: dict[str, Any] = {
            "schema_version": "1.0",
            "opportunity_id": oid,
            "revision": revision,
            **blueprint.requirement.model_dump(exclude_none=True),
        }
        target = _platform_target(body)
        body["platform"] = {"target": target}
        app = body.get("app")
        if isinstance(app, dict):
            app.setdefault("application_id", app.get("bundle_id"))
            if target == "android":
                app.setdefault("min_android_sdk", "24")
    else:
        feature_items = blueprint.keywords or ["核心流程", "离线使用", "本地存储"]
        bundle_suffix = app_token.replace("-", "") or "demoapp"
        body = {
            "schema_version": "1.0",
            "opportunity_id": oid,
            "revision": revision,
            "platform": {"target": "android"},
            "app": {
                "name": blueprint.app_name,
                "bundle_id": f"com.hunter.{bundle_suffix}",
                "application_id": f"com.hunter.{bundle_suffix}",
                "version": "1.0.0",
                "build": "1",
                "min_android_sdk": "24",
            },
            "features": [
                {
                    "id": "home",
                    "type": "list",
                    "title": "核心功能",
                    "items": feature_items[:8],
                }
            ],
            "core_logic": {
                "persistence": "SharedPreferences",
                "description": blueprint.core_logic,
            },
            "ui_layout": {
                "navigation": "stack",
                "screens": [blueprint.ui_layout],
            },
            "branding": {
                "primary_color": "#007AFF",
                "icon_text": blueprint.app_name[:1] if blueprint.app_name else "A",
            },
            "store": {
                "subtitle": blueprint.app_name,
                "description": blueprint.core_logic,
                "keywords": blueprint.keywords,
                "privacy_url": "https://example.com/privacy",
            },
            "budget": {"max_features": 8, "max_hours": 2.0},
        }

    if blueprint.data_quality:
        body["data_quality"] = blueprint.data_quality
    if blueprint.evidence:
        body["evidence"] = [e.model_dump() for e in blueprint.evidence]

    return body


def _http_json(
    *,
    url: str,
    body: dict[str, Any] | None,
    method: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    api_token = os.getenv("CRAFTSMAN_API_TOKEN")
    if api_token:
        headers["X-API-Token"] = api_token
    headers["X-Contract-Version"] = _requested_contract_version()
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        try:
            payload = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            payload = {}
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            code = err.get("code", "http_error")
            message = err.get("message", detail)
            retryable = bool(err.get("retryable"))
            raise CraftsmanHTTPError(
                f"craftsman HTTP {exc.code} [{code}] retryable={retryable}: {message}",
                code=str(code),
                status_code=int(exc.code),
                retryable=retryable,
            ) from exc
        raise RuntimeError(f"craftsman HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"craftsman unreachable: {exc.reason}") from exc
    payload = json.loads(content)
    if isinstance(payload, dict):
        _ensure_contract_compatibility(payload)
    return payload


def run_analyze(
    requirement: dict[str, Any],
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """调用 Agent B Gate（同步 analyze）。"""
    oid = requirement["opportunity_id"]
    url = f"{base_url.rstrip('/')}/v1/opportunities/{oid}/analyze"
    return _with_retry(
        lambda: _http_json(url=url, body=requirement, method="POST", timeout_seconds=timeout_seconds)
    )


def run_sync_implementation(
    requirement: dict[str, Any],
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    """调用 Agent B 的同步实现接口并返回 JSON。"""
    url = f"{base_url.rstrip('/')}/v1/runs/sync-implement"
    return _with_retry(
        lambda: _http_json(
            url=url,
            body={"requirement": requirement},
            method="POST",
            timeout_seconds=timeout_seconds,
        )
    )


def start_implementation(
    requirement: dict[str, Any],
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Trigger async implementation and return run envelope."""
    oid = requirement["opportunity_id"]
    url = f"{base_url.rstrip('/')}/v1/opportunities/{oid}/implement"
    body = {"opportunity_id": oid, "requirement": requirement}
    return _with_retry(
        lambda: _http_json(url=url, body=body, method="POST", timeout_seconds=timeout_seconds)
    )


def get_run_status(
    run_id: str,
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Fetch async run status and optional feedback."""
    url = f"{base_url.rstrip('/')}/v1/runs/{run_id}"
    return _with_retry(
        lambda: _http_json(url=url, body=None, method="GET", timeout_seconds=timeout_seconds)
    )


def get_run_events(
    run_id: str,
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 30.0,
    after_id: int = 0,
    limit: int = 200,
) -> dict[str, Any]:
    """Fetch run phase events emitted by Agent B."""
    url = (
        f"{base_url.rstrip('/')}/v1/runs/{run_id}/events"
        f"?after_id={max(after_id, 0)}&limit={max(limit, 1)}"
    )
    return _with_retry(
        lambda: _http_json(url=url, body=None, method="GET", timeout_seconds=timeout_seconds)
    )


def wait_for_run_completion(
    run_id: str,
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 600.0,
    poll_interval_seconds: float = 2.0,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Poll async run until terminal state and return terminal feedback payload."""
    started = datetime.now(timezone.utc).timestamp()
    terminal = {"failed", "ready_for_release", "submitted", "platform_unavailable", "cancelled", "implementation_complete"}
    after_id = 0
    while True:
        row = get_run_status(run_id, base_url=base_url, timeout_seconds=30.0)
        events = get_run_events(
            run_id,
            base_url=base_url,
            timeout_seconds=30.0,
            after_id=after_id,
            limit=200,
        )
        stream = events.get("events") if isinstance(events, dict) else None
        if isinstance(stream, list) and on_event is not None and stream:
            for event in stream:
                if isinstance(event, dict):
                    on_event(event)
        if isinstance(events, dict):
            after_id = int(events.get("next_after_id") or after_id)
        status = str(row.get("status", ""))
        if status in terminal:
            feedback = row.get("feedback")
            if isinstance(feedback, dict):
                return feedback
            return {
                "run_id": run_id,
                "opportunity_id": row.get("opportunity_id"),
                "revision": row.get("revision"),
                "agent_b_status": (
                    "implementation_failed"
                    if status == "failed"
                    else ("implementation_complete" if status == "implementation_complete" else status)
                ),
                "reasons": [row.get("error_message")] if row.get("error_message") else [],
            }
        if datetime.now(timezone.utc).timestamp() - started > timeout_seconds:
            raise RuntimeError(f"craftsman async run timeout: run_id={run_id}")
        import time

        time.sleep(max(poll_interval_seconds, 0.2))

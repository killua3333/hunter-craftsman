"""Hunter (Agent A) 与 Craftsman (Agent B) 的最小联通桥接。"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from hunter.schemas import AppOpportunityBlueprint


def _safe_token(value: str, *, fallback: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    if token:
        return token[:24]
    return fallback


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
            **blueprint.requirement.model_dump(),
        }
    else:
        feature_items = blueprint.keywords or ["核心流程", "离线使用", "本地存储"]
        bundle_suffix = app_token.replace("-", "") or "demoapp"
        body = {
            "schema_version": "1.0",
            "opportunity_id": oid,
            "revision": revision,
            "app": {
                "name": blueprint.app_name,
                "bundle_id": f"com.hunter.{bundle_suffix}",
                "version": "1.0.0",
                "build": "1",
                "min_ios": "17.0",
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
                "persistence": "UserDefaults",
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
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"craftsman HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"craftsman unreachable: {exc.reason}") from exc
    return json.loads(content)


def run_analyze(
    requirement: dict[str, Any],
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """调用 Agent B Gate（同步 analyze）。"""
    oid = requirement["opportunity_id"]
    url = f"{base_url.rstrip('/')}/v1/opportunities/{oid}/analyze"
    return _http_json(url=url, body=requirement, method="POST", timeout_seconds=timeout_seconds)


def run_sync_implementation(
    requirement: dict[str, Any],
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    """调用 Agent B 的同步实现接口并返回 JSON。"""
    url = f"{base_url.rstrip('/')}/v1/runs/sync-implement"
    return _http_json(
        url=url,
        body={"requirement": requirement},
        method="POST",
        timeout_seconds=timeout_seconds,
    )

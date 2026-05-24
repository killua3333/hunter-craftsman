"""将 Agent A 常见 JSON 变体规范为 AppOpportunityBlueprint 可校验结构。"""

from __future__ import annotations

import json
import re
from typing import Any

_FEATURE_TYPES = frozenset({"list", "form", "detail", "tab_root"})


def _slug_id(value: str, *, fallback: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "-", str(value)).strip("-").lower()
    return (token[:32] if token else fallback)


def coerce_string_list(value: Any) -> list[str]:
    """字符串、逗号分隔串、对象数组 → 字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if "," in text or "，" in text:
            parts = re.split(r"[,，]", text)
            return [p.strip() for p in parts if p.strip()]
        return [text]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    out.append(s)
            elif isinstance(item, dict):
                name = (item.get("name") or item.get("title") or "").strip()
                desc = (item.get("description") or item.get("snippet") or "").strip()
                if name and desc:
                    out.append(f"{name}: {desc}")
                elif name:
                    out.append(name)
                elif desc:
                    out.append(desc)
            elif item is not None:
                s = str(item).strip()
                if s:
                    out.append(s)
        return out
    return []


def _normalize_feature(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "id": f"feature-{index}",
            "type": "list",
            "title": f"功能 {index + 1}",
            "items": coerce_string_list(raw),
        }
    title = (raw.get("title") or raw.get("name") or f"功能 {index + 1}").strip()
    fid = raw.get("id") or raw.get("name") or title
    ftype = raw.get("type") or "list"
    if ftype not in _FEATURE_TYPES:
        ftype = "list"
    items = coerce_string_list(raw.get("items"))
    desc = raw.get("description")
    if isinstance(desc, str) and desc.strip() and desc.strip() not in items:
        items = [desc.strip(), *items]
    return {
        "id": _slug_id(str(fid), fallback=f"feature-{index}"),
        "type": ftype,
        "title": title,
        "items": items,
    }


def _normalize_store(store: Any) -> dict[str, Any] | None:
    if not isinstance(store, dict):
        return None
    out = dict(store)
    out["keywords"] = coerce_string_list(out.get("keywords"))
    return out


def normalize_blueprint_dict(data: dict[str, Any]) -> dict[str, Any]:
    """在 Pydantic 校验前修补模型常见字段偏差。"""
    out = dict(data)
    if isinstance(out.get("keywords"), str):
        out["keywords"] = coerce_string_list(out["keywords"])

    req = out.get("requirement")
    if not isinstance(req, dict):
        return out

    req = dict(req)
    platform = req.get("platform")
    if not isinstance(platform, dict):
        req["platform"] = {"target": "android"}
    else:
        target = str(platform.get("target") or "").strip().lower()
        req["platform"] = {"target": target if target in {"android", "ios"} else "android"}
    if "data_quality" in req and not out.get("data_quality"):
        out["data_quality"] = req.pop("data_quality")
    if "evidence" in req and not out.get("evidence"):
        out["evidence"] = req.pop("evidence")
    features = req.get("features")
    if isinstance(features, list):
        req["features"] = [_normalize_feature(f, i) for i, f in enumerate(features)]

    store = _normalize_store(req.get("store"))
    if store is not None:
        req["store"] = store
        if not out.get("keywords"):
            out["keywords"] = list(store.get("keywords") or [])

    app = req.get("app")
    if isinstance(app, dict):
        app = dict(app)
        if app.get("bundle_id") and not app.get("application_id"):
            app["application_id"] = app["bundle_id"]
        target = (req.get("platform") or {}).get("target")
        if target == "android" and not app.get("min_android_sdk"):
            app["min_android_sdk"] = "24"
        req["app"] = app
        if app.get("name") and not str(out.get("app_name") or "").strip():
            out["app_name"] = app["name"]

    core = req.get("core_logic")
    if isinstance(core, dict) and core.get("description") and not str(out.get("core_logic") or "").strip():
        out["core_logic"] = core["description"]

    ui = req.get("ui_layout")
    if isinstance(ui, dict) and ui.get("screens") and not str(out.get("ui_layout") or "").strip():
        screens = ui.get("screens")
        if isinstance(screens, list):
            out["ui_layout"] = "；".join(str(s) for s in screens if s)
        elif isinstance(screens, str):
            out["ui_layout"] = screens

    out["requirement"] = req
    return out

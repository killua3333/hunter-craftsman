"""将 Agent A 常见 JSON 变体规范为 AppOpportunityBlueprint 可校验结构。"""

from __future__ import annotations

import json
import re
from typing import Any

_FEATURE_TYPES = frozenset({"list", "form", "detail", "tab_root"})
_FEATURE_TYPE_ALIASES = {
    "core": "list",
    "main": "list",
    "screen": "list",
    "widget": "list",
}
_NAVIGATION_VALUES = frozenset({"stack", "tab", "single"})
_NAVIGATION_ALIASES = {
    "tab_root": "tab",
    "tabs": "tab",
    "bottom_tab": "tab",
    "bottom_tabs": "tab",
    "navigation": "stack",
    "nav_stack": "stack",
    "one_screen": "single",
    "single_screen": "single",
}


def _normalize_ui_layout(ui: Any) -> dict[str, Any]:
    """ui_layout.navigation 仅允许 stack|tab|single（模型常误写 tab_root）。"""
    if not isinstance(ui, dict):
        return {"navigation": "single", "screens": ["主屏"]}
    out = dict(ui)
    nav = str(out.get("navigation") or "").strip().lower()
    if nav in _NAVIGATION_VALUES:
        out["navigation"] = nav
    elif nav in _NAVIGATION_ALIASES:
        out["navigation"] = _NAVIGATION_ALIASES[nav]
    else:
        screens = out.get("screens")
        if isinstance(screens, list) and len(screens) > 1:
            out["navigation"] = "tab"
        else:
            out["navigation"] = "single"
    screens = out.get("screens")
    if isinstance(screens, str) and screens.strip():
        out["screens"] = [screens.strip()]
    elif not isinstance(screens, list) or not screens:
        out["screens"] = ["主屏"]
    else:
        out["screens"] = [str(s).strip() for s in screens if str(s).strip()]
    return out


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
    ftype = str(raw.get("type") or "list").strip().lower()
    if ftype not in _FEATURE_TYPES:
        ftype = _FEATURE_TYPE_ALIASES.get(ftype, "list")
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


def _coerce_evidence_items(value: Any) -> list[dict[str, str]]:
    """字符串列表或 evidence 对象 → EvidenceItem 形状。"""
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for i, item in enumerate(value):
        if isinstance(item, dict):
            query = str(item.get("query") or item.get("title") or f"evidence-{i + 1}").strip()
            source = str(item.get("source") or "assumption://autopilot").strip()
            snippet = str(item.get("snippet") or item.get("text") or "").strip()
            if snippet:
                out.append({"query": query, "source": source, "snippet": snippet})
        elif isinstance(item, str) and item.strip():
            text = item.strip()
            out.append(
                {
                    "query": text[:80],
                    "source": "assumption://play-research",
                    "snippet": text,
                }
            )
    return out


def _slug_bundle_id(name: str) -> str:
    slug = _slug_id(name, fallback="mvp")
    return f"com.hunter.{slug.replace('-', '')[:24]}"


def _generic_label(text: str) -> bool:
    value = str(text or "").strip().lower()
    if not value:
        return True
    generic_tokens = {
        "main",
        "home",
        "screen",
        "page",
        "main screen",
        "home screen",
        "主屏",
        "首页",
        "主页",
        "功能",
        "核心功能",
    }
    return value in generic_tokens


def _apply_product_quality_self_check(req: dict[str, Any]) -> None:
    quality = dict(req.get("product_quality") or {})
    risks = [str(r).strip() for r in quality.get("risks") or [] if str(r).strip()]
    features = req.get("features") if isinstance(req.get("features"), list) else []
    ui = req.get("ui_layout") if isinstance(req.get("ui_layout"), dict) else {}
    screens = ui.get("screens") if isinstance(ui.get("screens"), list) else []
    core_logic = req.get("core_logic") if isinstance(req.get("core_logic"), dict) else {}

    if any(_generic_label(f.get("title")) for f in features if isinstance(f, dict)):
        risks.append("generic_feature_titles")
    if any(_generic_label(screen) for screen in screens):
        risks.append("generic_screen_definition")
    if len(str(core_logic.get("description") or "").strip()) < 4:
        risks.append("thin_core_logic_description")

    seen: list[str] = []
    for risk in risks:
        if risk not in seen:
            seen.append(risk)
    quality["risks"] = seen
    if any(
        risk in seen
        for risk in {
            "generic_feature_titles",
            "thin_interaction_detail",
            "generic_screen_definition",
        }
    ):
        quality["interaction_depth"] = "generic"
    req["product_quality"] = quality


def _flatten_discovery_shape(data: dict[str, Any]) -> dict[str, Any]:
    """Autopilot 常见变体：app_idea / opportunity 嵌套 → 扁平 AppOpportunityBlueprint。"""
    out = dict(data)
    app_idea = out.pop("app_idea", None)
    if isinstance(app_idea, dict):
        title = (app_idea.get("title") or app_idea.get("name") or "").strip()
        if title and not str(out.get("app_name") or "").strip():
            out["app_name"] = title
        tagline = (app_idea.get("tagline") or app_idea.get("one_line_description") or "").strip()
        if tagline and not str(out.get("core_logic") or "").strip():
            out["core_logic"] = tagline

    opportunity = out.pop("opportunity", None)
    if isinstance(opportunity, dict):
        if not out.get("evidence"):
            out["evidence"] = _coerce_evidence_items(opportunity.get("evidence"))
        if not str(out.get("core_logic") or "").strip():
            pains = coerce_string_list(opportunity.get("pain_points"))
            if pains:
                out["core_logic"] = pains[0][:200]
        if not out.get("data_quality"):
            out["data_quality"] = "mixed"

    if not out.get("data_quality"):
        out["data_quality"] = "assumption"
    if not out.get("evidence"):
        out["evidence"] = _coerce_evidence_items(out.get("evidence"))
    return out


def _ensure_requirement_defaults(req: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    """补全 requirement 缺失块（发现模式常漏 app / branding / store）。"""
    app_name = str(out.get("app_name") or "MVP App").strip() or "MVP App"
    if not isinstance(req.get("app"), dict):
        req["app"] = {
            "name": app_name,
            "bundle_id": _slug_bundle_id(app_name),
            "min_android_sdk": "24",
        }
    core = req.get("core_logic")
    if not isinstance(core, dict):
        desc = str(out.get("core_logic") or "本地 MVP").strip()
        req["core_logic"] = {
            "persistence": "SharedPreferences",
            "description": desc,
        }
    elif isinstance(core, dict):
        core = dict(core)
        if not core.get("description"):
            parts: list[str] = []
            if core.get("main_function"):
                parts.append(str(core["main_function"]).strip())
            parts.extend(coerce_string_list(core.get("key_actions")))
            core["description"] = "；".join(p for p in parts if p)[:500] or str(
                out.get("core_logic") or "本地 MVP"
            )
        if not core.get("persistence"):
            core["persistence"] = "SharedPreferences"
        core.pop("main_function", None)
        core.pop("key_actions", None)
        req["core_logic"] = core

    ui = req.get("ui_layout")
    if not isinstance(ui, dict):
        summary = str(out.get("ui_layout") or "单屏列表").strip()
        req["ui_layout"] = {"navigation": "single", "screens": [summary]}
    else:
        req["ui_layout"] = _normalize_ui_layout(ui)

    if not isinstance(req.get("branding"), dict):
        req["branding"] = {"primary_color": "#4A90D9", "icon_text": app_name[:1] or "A"}

    store = req.get("store")
    if not isinstance(store, dict):
        req["store"] = {
            "subtitle": app_name[:30],
            "description": str(out.get("core_logic") or app_name)[:200],
            "keywords": list(out.get("keywords") or [])[:8] or ["工具", "效率"],
            "privacy_url": "https://example.com/privacy",
        }
    if not isinstance(req.get("budget"), dict):
        req["budget"] = {"max_features": 8, "max_hours": 2.0}
    if not isinstance(req.get("product_quality"), dict):
        req["product_quality"] = {
            "target": "verified",
            "interaction_depth": "task_focused",
            "risks": [],
        }
    else:
        product_quality = dict(req["product_quality"])
        target = str(product_quality.get("target") or "").strip().lower()
        if target not in {"verified", "demo"}:
            product_quality["target"] = "verified"
        depth = str(product_quality.get("interaction_depth") or "").strip().lower()
        if depth not in {"generic", "task_focused", "polished"}:
            product_quality["interaction_depth"] = "task_focused"
        risks = product_quality.get("risks")
        if not isinstance(risks, list):
            product_quality["risks"] = coerce_string_list(risks)
        req["product_quality"] = product_quality

    features = req.get("features")
    if not isinstance(features, list) or not features:
        req["features"] = [
            {
                "id": "main",
                "type": "list",
                "title": "核心功能",
                "items": [str(out.get("core_logic") or "主流程")[:120]],
            }
        ]
    _apply_product_quality_self_check(req)
    return req


def normalize_blueprint_dict(data: dict[str, Any]) -> dict[str, Any]:
    """在 Pydantic 校验前修补模型常见字段偏差。"""
    out = _flatten_discovery_shape(data)
    if isinstance(out.get("keywords"), str):
        out["keywords"] = coerce_string_list(out["keywords"])
    if isinstance(out.get("evidence"), list):
        ev = _coerce_evidence_items(out["evidence"])
        if ev:
            out["evidence"] = ev

    req = out.get("requirement")
    if not isinstance(req, dict):
        return out

    req = dict(req)
    req = _ensure_requirement_defaults(req, out)
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
        req["features"] = [
            _normalize_feature(f, i) for i, f in enumerate(features[:6])
        ]

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

    req["ui_layout"] = _normalize_ui_layout(req.get("ui_layout"))

    ui = req.get("ui_layout")
    if isinstance(ui, dict) and ui.get("screens") and not str(out.get("ui_layout") or "").strip():
        screens = ui.get("screens")
        if isinstance(screens, list):
            out["ui_layout"] = "；".join(str(s) for s in screens if s)
        elif isinstance(screens, str):
            out["ui_layout"] = screens
    if not str(out.get("ui_layout") or "").strip():
        out["ui_layout"] = "单屏列表"
    if not out.get("keywords"):
        out["keywords"] = list((req.get("store") or {}).get("keywords") or ["工具", "效率"])

    out["requirement"] = req
    return out

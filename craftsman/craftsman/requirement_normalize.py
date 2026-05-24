"""实现前规范化 requirement（不删字段）。"""

from __future__ import annotations

import copy
import re
from typing import Any

from craftsman.config import settings

_NAV_VIEW = re.compile(r"\bNavigationView\b")
_DEFAULT_PRIVACY = "https://example.com/privacy"


def _rewrite_strings(value: Any) -> Any:
    if isinstance(value, str):
        return _NAV_VIEW.sub("NavigationStack", value)
    if isinstance(value, list):
        return [_rewrite_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_strings(val) for key, val in value.items()}
    return value


def _slug_token(name: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "", name).lower()
    return (token[:20] or "autopilot")


def soft_fill_requirement(req: dict[str, Any]) -> dict[str, Any]:
    """Soft Gate：补全缺省字段、截断 features，便于自动跑通。"""
    out = copy.deepcopy(req)
    platform = out.get("platform")
    if not isinstance(platform, dict):
        out["platform"] = {"target": "android"}
    target = str(out["platform"].get("target") or "android").lower()
    if target not in {"android", "ios"}:
        target = "android"
    out["platform"] = {"target": target}

    app = out.setdefault("app", {})
    if not isinstance(app, dict):
        app = {}
        out["app"] = app
    name = str(app.get("name") or "").strip() or "Autopilot App"
    app["name"] = name
    if not app.get("bundle_id"):
        app["bundle_id"] = f"com.hunter.{_slug_token(name)}"
    if target == "android":
        app.setdefault("application_id", app["bundle_id"])
        app.setdefault("min_android_sdk", "24")

    features = out.get("features")
    if not isinstance(features, list) or not features:
        features = [
            {
                "id": "main",
                "type": "list",
                "title": name,
                "items": ["核心功能", "本地存储", "简洁界面"],
            }
        ]
        out["features"] = features
    max_features = int((out.get("budget") or {}).get("max_features") or settings.max_features)
    if len(features) > max_features:
        out["features"] = features[:max_features]
    for feat in out["features"]:
        if isinstance(feat, dict) and not feat.get("items"):
            feat["items"] = [str(feat.get("title") or "功能")]

    core = out.setdefault("core_logic", {})
    if not isinstance(core, dict):
        core = {}
        out["core_logic"] = core
    if not core.get("persistence"):
        core["persistence"] = "SharedPreferences" if target == "android" else "UserDefaults"
    core.setdefault("description", f"{name} 本地 MVP")

    ui = out.setdefault("ui_layout", {})
    if not isinstance(ui, dict):
        ui = {}
        out["ui_layout"] = ui
    ui.setdefault("navigation", "single")
    ui.setdefault("screens", [f"{name} 主屏"])

    branding = out.setdefault("branding", {})
    if not isinstance(branding, dict):
        branding = {}
        out["branding"] = branding
    branding.setdefault("primary_color", "#007AFF")
    branding.setdefault("icon_text", (name[:1] or "A"))

    store = out.setdefault("store", {})
    if not isinstance(store, dict):
        store = {}
        out["store"] = store
    store.setdefault("subtitle", name[:30])
    store.setdefault("description", core.get("description", name))
    keywords = store.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        store["keywords"] = [name[:12], "工具", "效率"]
    elif isinstance(keywords, str):
        store["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]
    store.setdefault("privacy_url", _DEFAULT_PRIVACY)

    budget = out.setdefault("budget", {})
    if not isinstance(budget, dict):
        budget = {}
        out["budget"] = budget
    budget.setdefault("max_features", settings.max_features)
    budget.setdefault("max_hours", 2.0)

    if not out.get("data_quality"):
        out["data_quality"] = "assumption"
    evidence = out.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        out["evidence"] = [
            {
                "query": "autopilot discovery",
                "source": "assumption://autopilot soft fill",
                "snippet": f"自动选定机会：{name}",
            }
        ]

    return out


def shrink_requirement_scope(req: dict[str, Any]) -> dict[str, Any]:
    """Implement 失败时缩小 scope：截断 features、简化 persistence。"""
    out = copy.deepcopy(req)
    features = out.get("features")
    if isinstance(features, list) and len(features) > 1:
        out["features"] = features[:1]
    features = out.get("features")
    if isinstance(features, list):
        for feat in features:
            if isinstance(feat, dict):
                items = feat.get("items")
                if isinstance(items, list) and len(items) > 2:
                    feat["items"] = items[:2]
    core = out.setdefault("core_logic", {})
    if isinstance(core, dict):
        persistence = str(core.get("persistence") or "").strip()
        if persistence in {"SwiftData", "SharedPreferences", "UserDefaults"}:
            core["persistence"] = "none"
            core["description"] = str(core.get("description") or "本地 MVP（缩 scope 重试）")
    budget = out.setdefault("budget", {})
    if isinstance(budget, dict):
        budget["max_features"] = min(int(budget.get("max_features") or settings.max_features), 3)
    out["_scope_retry"] = True
    return out


def normalize_requirement(req: dict[str, Any]) -> dict[str, Any]:
    """保留全部字段；将文案中的 NavigationView 统一为 NavigationStack。"""
    out = copy.deepcopy(req)
    out = _rewrite_strings(out)
    platform = out.get("platform")
    if not isinstance(platform, dict):
        out["platform"] = {"target": "android"}
    else:
        target = str(platform.get("target") or "").strip().lower()
        out["platform"] = {"target": target if target in {"android", "ios"} else "android"}
    app = out.get("app")
    if isinstance(app, dict):
        if app.get("bundle_id") and not app.get("application_id"):
            app["application_id"] = app["bundle_id"]
        if out["platform"]["target"] == "android" and not app.get("min_android_sdk"):
            app["min_android_sdk"] = "24"

    mode = settings.gate_mode.strip().lower()
    if mode == "soft":
        out = soft_fill_requirement(out)
    return out

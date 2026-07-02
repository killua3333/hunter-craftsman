from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_implementation_plan(
    workspace: Path,
    requirement: dict[str, Any],
) -> dict[str, Any]:
    features = requirement.get("features") or []
    app = requirement.get("app") if isinstance(requirement.get("app"), dict) else {}
    core_logic = requirement.get("core_logic") if isinstance(requirement.get("core_logic"), dict) else {}
    screens = (requirement.get("ui_layout") or {}).get("screens") or []
    main_flow = _feature_title(features[0]) if features else app.get("name", "main")
    plan = {
        "app_name": app.get("name"),
        "main_flow": main_flow,
        "core_features": [_feature_title(item) for item in features[:3]],
        "screens": screens[:4] or ["Main"],
        "local_state": core_logic.get("persistence") or "SharedPreferences",
        "data_model": _derive_data_model(features, core_logic),
        "user_actions": _derive_user_actions(features),
    }
    (workspace / "implementation_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return plan


def evaluate_app_quality(
    *,
    backend_mode: str,
    compile_exit_code: int,
    project_dir: Path,
    workspace: Path,
    requirement: dict[str, Any],
    icon_path: Path,
    screenshots: list[str],
    metadata_root: Path,
    verification: str,
) -> dict[str, Any]:
    score = 100
    failure_classes: list[str] = []
    repair_suggestions: list[str] = []
    warnings: list[str] = []
    main_interactions: list[str] = []
    persistence_evidence: list[str] = []

    if compile_exit_code != 0 and backend_mode in {"android_gradle", "android_gradle_docker", "macos_xcode"}:
        score -= 45
        failure_classes.append("build_failed")
        repair_suggestions.append("Fix native build errors before release")

    if backend_mode in {"android_gradle", "android_gradle_docker"}:
        ui = _inspect_android_ui(project_dir, requirement)
        main_interactions = ui["main_interactions"]
        persistence_evidence = ui["persistence_evidence"]
        score -= ui["penalty"]
        failure_classes.extend(ui["failure_classes"])
        repair_suggestions.extend(ui["repair_suggestions"])
    else:
        if verification != "verified":
            score -= 15
            warnings.append("native verification skipped")

    store_asset_penalty = 0
    if not icon_path.is_file():
        store_asset_penalty += 8
        failure_classes.append("poor_store_assets")
        repair_suggestions.append("Generate a usable store icon")
    if len([p for p in screenshots if Path(p).is_file()]) < 1:
        store_asset_penalty += 10
        failure_classes.append("poor_store_assets")
        repair_suggestions.append("Generate at least one screenshot that shows the core feature")
    score -= store_asset_penalty

    metadata_penalty = _metadata_penalty(metadata_root)
    if metadata_penalty:
        score -= metadata_penalty
        failure_classes.append("poor_store_assets")
        repair_suggestions.append("Complete store title, subtitle, description, and keywords")

    if _looks_generic_template(project_dir, requirement):
        score -= 12
        failure_classes.append("generic_template")
        repair_suggestions.append("Add requirement-specific copy, state, and core flow")


    if _pain_topic_as_feature(requirement):
        score -= 30
        failure_classes.append("weak_core_flow")
        repair_suggestions.append("Convert review pain labels into real product actions before release")
        warnings.append("features look like pain point labels instead of product features")
    score = max(0, min(100, score))
    failure_classes = _dedupe(failure_classes)
    repair_suggestions = _dedupe(repair_suggestions)
    release_ready = score >= 75 and "build_failed" not in failure_classes and "empty_ui" not in failure_classes
    polish_required = 60 <= score < 75
    return {
        "quality_score": score,
        "release_ready": release_ready,
        "polish_required": polish_required,
        "failure_classes": failure_classes,
        "repair_suggestions": repair_suggestions,
        "screenshots": screenshots,
        "main_interactions": main_interactions,
        "persistence_evidence": persistence_evidence,
        "warnings": warnings,
        "thresholds": {
            "release_ready": 75,
            "needs_polish": 60,
        },
    }



def _pain_topic_as_feature(requirement: dict[str, Any]) -> bool:
    pain_topics = {
        "ad", "ads", "advertising", "subscription", "payment", "crash", "bug",
        "notification spam", "sync issue", "missing feature",
        "\u5e7f\u544a", "\u8ba2\u9605", "\u4ed8\u8d39", "\u5d29\u6e83", "\u95ea\u9000",
        "\u901a\u77e5\u9a9a\u6270", "\u529f\u80fd\u7f3a\u5931", "\u540c\u6b65\u95ee\u9898",
        "\u65e0\u6cd5\u7f16\u8f91", "\u6743\u9650\u8fc7\u591a",
    }
    for feature in requirement.get("features") or []:
        title = _feature_title(feature).strip().lower()
        if title in pain_topics:
            return True
    return False
def _feature_title(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("title") or item.get("name") or item.get("id") or "feature")
    return str(item or "feature")


def _derive_data_model(features: list[Any], core_logic: dict[str, Any]) -> list[str]:
    model = []
    for feature in features[:3]:
        title = _feature_title(feature)
        model.append(f"{title}: local state")
    if not model:
        model.append(str(core_logic.get("description") or "local item"))
    return model


def _derive_user_actions(features: list[Any]) -> list[str]:
    actions = []
    for feature in features[:3]:
        actions.append(f"open {_feature_title(feature)}")
    return actions or ["open app", "use main action"]


def _inspect_android_ui(project_dir: Path, requirement: dict[str, Any]) -> dict[str, Any]:
    src_root = project_dir / "app" / "src" / "main" / "java"
    candidates = list(src_root.rglob("MainActivity.kt")) if src_root.exists() else []
    if not candidates:
        return {
            "penalty": 45,
            "failure_classes": ["empty_ui"],
            "repair_suggestions": ["Generate Kotlin/Compose MainActivity.kt"],
            "main_interactions": [],
            "persistence_evidence": [],
        }
    text = candidates[0].read_text(encoding="utf-8", errors="ignore")
    penalty = 0
    failures: list[str] = []
    suggestions: list[str] = []
    interactions = _find_tokens(
        text,
        {
            "button": "Button(",
            "text_field": "TextField(",
            "outlined_text_field": "OutlinedTextField(",
            "clickable": ".clickable",
            "checkbox": "Checkbox(",
            "switch": "Switch(",
            "slider": "Slider(",
        },
    )
    persistence = _find_tokens(
        text,
        {
            "remember": "remember",
            "mutable_state": "mutableState",
            "shared_preferences": "SharedPreferences",
            "get_shared_preferences": "getSharedPreferences",
            "remember_saveable": "rememberSaveable",
        },
    )
    if "setContent" not in text:
        penalty += 35
        failures.append("empty_ui")
        suggestions.append("MainActivity must include Compose setContent")
    if not interactions:
        penalty += 25
        failures.append("empty_ui")
        suggestions.append("Provide at least one interactive control")
    if not persistence:
        penalty += 15
        failures.append("no_persistence")
        suggestions.append("Use remember/mutableState or SharedPreferences for local state")
    if _weak_core_flow(text, requirement):
        penalty += 15
        failures.append("weak_core_flow")
        suggestions.append("Make the main screen directly express the requested core feature")
    return {
        "penalty": penalty,
        "failure_classes": failures,
        "repair_suggestions": suggestions,
        "main_interactions": interactions,
        "persistence_evidence": persistence,
    }


def _weak_core_flow(text: str, requirement: dict[str, Any]) -> bool:
    feature_words = []
    for feature in requirement.get("features") or []:
        if isinstance(feature, dict):
            feature_words.extend(str(feature.get("title") or "").lower().split())
            for item in feature.get("items") or []:
                feature_words.extend(str(item).lower().split()[:3])
    feature_words = [w.strip(" ,.;:!?") for w in feature_words if len(w.strip(" ,.;:!?")) >= 4]
    if not feature_words:
        return False
    lower = text.lower()
    hits = sum(1 for word in set(feature_words[:20]) if word in lower)
    return hits == 0


def _looks_generic_template(project_dir: Path, requirement: dict[str, Any]) -> bool:
    src_root = project_dir / "app" / "src" / "main" / "java"
    files = list(src_root.rglob("*.kt")) if src_root.exists() else []
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in files[:8])
    app = requirement.get("app") if isinstance(requirement.get("app"), dict) else {}
    app_name = str(app.get("name") or "").strip().lower()
    if app_name and app_name in text.lower():
        return False
    generic_markers = ("core feature", "sample", "placeholder", "todo", "lorem")
    return any(marker in text.lower() for marker in generic_markers)


def _metadata_penalty(metadata_root: Path) -> int:
    candidates = [
        metadata_root / "zh-CN",
        metadata_root,
    ]
    files = ("name.txt", "subtitle.txt", "description.txt", "keywords.txt")
    for root in candidates:
        if root.is_dir() and all((root / name).is_file() and (root / name).read_text(encoding="utf-8").strip() for name in files):
            return 0
    return 8


def _find_tokens(text: str, token_map: dict[str, str]) -> list[str]:
    return [name for name, token in token_map.items() if token in text]


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out

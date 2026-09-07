from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PAIN_TOPIC_TITLES = {
    "ad", "ads", "advertising", "subscription", "payment", "crash", "bug",
    "notification spam", "sync issue", "missing feature", "login", "cloud sync",
    "广告", "订阅", "付费", "崩溃", "闪退", "通知骚扰", "功能缺失", "同步问题",
    "无法编辑", "权限过多", "登录", "云同步",
}
FORBIDDEN_SCOPE_KEYWORDS = {
    "login", "account", "subscription", "payment", "server", "backend", "cloud sync",
    "登录", "账号", "订阅", "支付", "服务器", "后端", "云同步",
}

RELEASE_QUALITY_THRESHOLD = 75
RELEASE_HARD_BLOCKERS = frozenset({
    "build_failed", "empty_ui", "weak_core_flow", "device_verification_missing",
})
NATIVE_VERIFICATION_BLOCKER = "native_verification_missing"
DEVICE_VERIFICATION_BLOCKER = "device_verification_missing"


def release_quality_gate(handoff: dict[str, Any]) -> dict[str, Any]:
    """Return the effective quality decision, including legacy advisory overrides."""
    report = (
        handoff.get("quality_report") if isinstance(handoff.get("quality_report"), dict) else {}
    )
    score = handoff.get("quality_score")
    if score is None:
        score = report.get("quality_score")
    release_ready = handoff.get("release_ready")
    if release_ready is None:
        release_ready = report.get("release_ready")
    failures = list(
        report.get("failure_classes") or handoff.get("quality_failure_classes") or []
    )
    if score is None:
        return {
            "passed": True,
            "quality_score": None,
            "release_ready": bool(release_ready),
            "failure_classes": failures,
        }
    try:
        score_int = int(score)
    except (TypeError, ValueError):
        score_int = 0
    hard_failures = sorted(set(failures) & RELEASE_HARD_BLOCKERS)
    passed = score_int >= RELEASE_QUALITY_THRESHOLD and not hard_failures
    return {
        "passed": passed,
        "quality_score": score_int,
        "release_ready": bool(release_ready),
        "effective_release_ready": passed,
        "legacy_advisory_override": passed and not bool(release_ready),
        "failure_classes": failures,
        "hard_failure_classes": hard_failures,
    }



def write_implementation_plan(
    workspace: Path,
    requirement: dict[str, Any],
) -> dict[str, Any]:
    features = _safe_features(requirement)[:3]
    app = requirement.get("app") if isinstance(requirement.get("app"), dict) else {}
    core_logic = requirement.get("core_logic") if isinstance(requirement.get("core_logic"), dict) else {}
    ui_layout = requirement.get("ui_layout") if isinstance(requirement.get("ui_layout"), dict) else {}
    screens = ui_layout.get("screens") or []
    core_features = [_feature_title(item) for item in features]
    main_flow = core_features[0] if core_features else str(app.get("name") or "main task")
    storage = str(core_logic.get("persistence") or "rememberSaveable + SharedPreferences when persistence is needed")
    plan = {
        "schema_version": 2,
        "app_name": app.get("name"),
        "primary_user_flow": main_flow,
        "main_flow": main_flow,
        "core_features": core_features,
        "screens": screens[:4] or ["Main"],
        "screen_states": {
            "home": f"Show {main_flow} entry point and current local data.",
            "empty": "Explain what the user can add or start first.",
            "input": "Let the user type, choose, toggle, or start the primary action.",
            "result": "Reflect the saved or calculated result immediately on screen.",
        },
        "local_state": storage,
        "local_storage": storage,
        "data_model": _derive_data_model(features, core_logic),
        "user_actions": _derive_user_actions(features),
        "acceptance_actions": _derive_acceptance_actions(features, main_flow),
        "forbidden_scope": ["login", "subscription", "payment", "cloud sync", "backend service"],
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
    device_acceptance_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failure_classes: list[str] = []
    repair_suggestions: list[str] = []
    warnings: list[str] = []
    manual_review_notes: list[str] = []
    main_interactions: list[str] = []
    persistence_evidence: list[str] = []

    ui = _empty_ui_result()
    if backend_mode in {"android_gradle", "android_gradle_docker"}:
        ui = _inspect_android_ui(project_dir, requirement)
        main_interactions = ui["main_interactions"]
        persistence_evidence = ui["persistence_evidence"]
    elif verification != "verified":
        warnings.append("native verification skipped")
        manual_review_notes.append("Native verification was skipped; inspect the build manually before release.")

    native_verification_required = backend_mode in {"android_gradle", "android_gradle_docker", "macos_xcode"}
    native_verification_missing = native_verification_required and verification != "verified"
    device_report = device_acceptance_report or {}
    device_verification_required = backend_mode in {"android_gradle", "android_gradle_docker"}
    device_verification_missing = device_verification_required and not bool(
        device_report.get("launch_verified")
    )

    core_flow_score = 100 - min(100, ui["core_flow_penalty"])
    ui_completeness_score = 100 - min(100, ui["ui_penalty"])
    persistence_score = 100 - min(100, ui["persistence_penalty"])
    store_asset_score = _store_asset_score(icon_path, screenshots, metadata_root)
    product_specificity_score = 100

    failure_classes.extend(ui["failure_classes"])
    repair_suggestions.extend(ui["repair_suggestions"])

    if compile_exit_code != 0 and backend_mode in {"android_gradle", "android_gradle_docker", "macos_xcode"}:
        failure_classes.append("build_failed")
        repair_suggestions.append("Fix native build errors before release")
        manual_review_notes.append("The native build must pass before the app can be evaluated as release-ready.")

    if store_asset_score < 80:
        failure_classes.append("poor_store_assets")
        repair_suggestions.append("Complete store icon, screenshots, title, subtitle, description, and keywords")

    if _looks_generic_template(project_dir, requirement):
        product_specificity_score -= 35
        failure_classes.append("generic_template")
        repair_suggestions.append("Add requirement-specific copy, local state, and a real core flow")
        manual_review_notes.append("The UI still looks like a generic generated template.")

    if _pain_topic_as_feature(requirement):
        core_flow_score -= 45
        product_specificity_score -= 30
        failure_classes.append("weak_core_flow")
        repair_suggestions.append("Convert review pain labels into product actions before release")
        warnings.append("features look like pain point labels instead of product features")

    if _has_forbidden_scope(requirement, project_dir):
        product_specificity_score -= 35
        failure_classes.append("scope_too_large")
        repair_suggestions.append("Remove login, payment, subscription, cloud sync, and backend dependencies")
        manual_review_notes.append("The generated app appears to include scope that this product line should avoid.")

    core_flow_score = _clamp_score(core_flow_score)
    ui_completeness_score = _clamp_score(ui_completeness_score)
    persistence_score = _clamp_score(persistence_score)
    store_asset_score = _clamp_score(store_asset_score)
    product_specificity_score = _clamp_score(product_specificity_score)

    build_score = 0 if (compile_exit_code != 0 and backend_mode in {"android_gradle", "android_gradle_docker", "macos_xcode"}) else 100
    weighted = round(
        core_flow_score * 0.28
        + ui_completeness_score * 0.24
        + persistence_score * 0.16
        + store_asset_score * 0.14
        + product_specificity_score * 0.18
    )
    if build_score == 0:
        weighted = min(weighted, 55)
    if native_verification_missing:
        weighted = min(weighted, RELEASE_QUALITY_THRESHOLD - 1)
        failure_classes.append(NATIVE_VERIFICATION_BLOCKER)
        repair_suggestions.append("Build and run the native app before release")
        manual_review_notes.append("当前版本仅可预览；完成原生编译和运行检查后才能发布。")
    if device_verification_missing:
        weighted = min(weighted, RELEASE_QUALITY_THRESHOLD - 1)
        failure_classes.append(DEVICE_VERIFICATION_BLOCKER)
        repair_suggestions.append("Install and launch the APK on an Android device or emulator")
        manual_review_notes.append("当前版本尚无设备启动证据，不能标记为建议发布。")

    # Scope findings are advisory; broad wording alone must not block a usable MVP.
    hard_blockers = RELEASE_HARD_BLOCKERS
    failure_classes = _dedupe(failure_classes)
    repair_suggestions = _dedupe(repair_suggestions)
    release_ready = (
        weighted >= RELEASE_QUALITY_THRESHOLD
        and not native_verification_missing
        and not device_verification_missing
        and not (set(failure_classes) & hard_blockers)
    )
    polish_required = 60 <= weighted < RELEASE_QUALITY_THRESHOLD or (
        weighted >= RELEASE_QUALITY_THRESHOLD and not release_ready
    )

    if not release_ready and weighted >= 60:
        manual_review_notes.append("可预览，但建议继续打磨后再上架。")
    elif release_ready:
        manual_review_notes.append("建议发布：核心流程、交互、本地状态和素材均达到当前门槛。")

    return {
        "schema_version": 2,
        "quality_score": int(_clamp_score(weighted)),
        "release_ready": release_ready,
        "polish_required": polish_required,
        "failure_classes": failure_classes,
        "repair_suggestions": repair_suggestions,
        "screenshots": screenshots,
        "main_interactions": main_interactions,
        "persistence_evidence": persistence_evidence,
        "device_acceptance": device_report,
        "device_launch_verified": bool(device_report.get("launch_verified")),
        "core_flow_device_verified": bool(device_report.get("core_flow_verified")),
        "persistence_device_verified": bool(device_report.get("persistence_verified")),
        "store_screenshot_source": "generated_marketing_mockup",
        "device_screenshots": list(device_report.get("device_screenshots") or []),
        "warnings": _dedupe(warnings),
        "manual_review_notes": _dedupe(manual_review_notes),
        "core_flow_score": core_flow_score,
        "ui_completeness_score": ui_completeness_score,
        "persistence_score": persistence_score,
        "store_asset_score": store_asset_score,
        "product_specificity_score": product_specificity_score,
        "thresholds": {
            "release_ready": 75,
            "needs_polish": 60,
        },
    }


def _empty_ui_result() -> dict[str, Any]:
    return {
        "ui_penalty": 0,
        "core_flow_penalty": 0,
        "persistence_penalty": 0,
        "failure_classes": [],
        "repair_suggestions": [],
        "main_interactions": [],
        "persistence_evidence": [],
    }


def _safe_features(requirement: dict[str, Any]) -> list[Any]:
    features = requirement.get("features")
    return features if isinstance(features, list) else []


def _feature_title(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("title") or item.get("name") or item.get("id") or "feature")
    return str(item or "feature")


def _derive_data_model(features: list[Any], core_logic: dict[str, Any]) -> list[str]:
    model = []
    for feature in features[:3]:
        title = _feature_title(feature)
        model.append(f"{title}: local state item")
    if not model:
        model.append(str(core_logic.get("description") or "local item"))
    return model


def _derive_user_actions(features: list[Any]) -> list[str]:
    actions = []
    for feature in features[:3]:
        title = _feature_title(feature)
        actions.append(f"open {title}")
        actions.append(f"change local state for {title}")
    return actions or ["open app", "use main action", "see local result"]


def _derive_acceptance_actions(features: list[Any], main_flow: str) -> list[str]:
    titles = [_feature_title(item) for item in features[:3]] or [main_flow]
    return [
        f"User can start or add {titles[0]} from the main screen.",
        "User can see an empty state before adding data.",
        "User can change local state and see the result without an account or server.",
    ]


def _inspect_android_ui(project_dir: Path, requirement: dict[str, Any]) -> dict[str, Any]:
    src_root = project_dir / "app" / "src" / "main" / "java"
    candidates = list(src_root.rglob("MainActivity.kt")) if src_root.exists() else []
    if not candidates:
        return {
            "ui_penalty": 85,
            "core_flow_penalty": 65,
            "persistence_penalty": 100,
            "failure_classes": ["empty_ui"],
            "repair_suggestions": ["Generate Kotlin/Compose MainActivity.kt"],
            "main_interactions": [],
            "persistence_evidence": [],
        }
    text = candidates[0].read_text(encoding="utf-8", errors="ignore")
    lower = text.lower()
    failures: list[str] = []
    suggestions: list[str] = []
    ui_penalty = 0
    core_flow_penalty = 0
    persistence_penalty = 0
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
            "floating_action_button": "FloatingActionButton(",
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
    state_labels = {
        "empty_state": any(token in lower for token in ("empty", "no items", "暂无", "还没有", "添加", "start by")),
        "input_state": bool(interactions),
        "result_state": any(token in lower for token in ("list", "lazycolumn", "result", "history", "saved", "完成", "记录")),
    }
    if "setContent" not in text:
        ui_penalty += 60
        failures.append("empty_ui")
        suggestions.append("MainActivity must include Compose setContent")
    if not interactions:
        ui_penalty += 45
        failures.append("empty_ui")
        suggestions.append("Provide at least one Button, TextField, Checkbox, Switch, Slider, or clickable control")
    if not any(state_labels.values()):
        ui_penalty += 20
        suggestions.append("Represent empty, input, and result states in the main screen")
    elif not all(state_labels.values()):
        ui_penalty += 8
    if not persistence:
        persistence_penalty += 75
        failures.append("no_persistence")
        suggestions.append("Use rememberSaveable/mutableState or SharedPreferences for local state")
    if _weak_core_flow(text, requirement):
        core_flow_penalty += 55
        failures.append("weak_core_flow")
        suggestions.append("Make the main screen directly express the requested core feature")
    return {
        "ui_penalty": ui_penalty,
        "core_flow_penalty": core_flow_penalty,
        "persistence_penalty": persistence_penalty,
        "failure_classes": failures,
        "repair_suggestions": suggestions,
        "main_interactions": interactions,
        "persistence_evidence": persistence,
    }


def _weak_core_flow(text: str, requirement: dict[str, Any]) -> bool:
    feature_words = []
    app = requirement.get("app") if isinstance(requirement.get("app"), dict) else {}
    feature_words.extend(str(app.get("name") or "").lower().split())
    for feature in _safe_features(requirement):
        if isinstance(feature, dict):
            feature_words.extend(str(feature.get("title") or "").lower().split())
            for item in feature.get("items") or []:
                feature_words.extend(str(item).lower().split()[:3])
        else:
            feature_words.extend(str(feature).lower().split())
    feature_words = [w.strip(" ,.;:!?()[]{}") for w in feature_words if len(w.strip(" ,.;:!?()[]{}")) >= 4]
    if not feature_words:
        return False
    lower = text.lower()
    hits = sum(1 for word in set(feature_words[:24]) if word in lower)
    return hits == 0


def _looks_generic_template(project_dir: Path, requirement: dict[str, Any]) -> bool:
    src_root = project_dir / "app" / "src" / "main" / "java"
    files = list(src_root.rglob("*.kt")) if src_root.exists() else []
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in files[:8])
    lower = text.lower()
    app = requirement.get("app") if isinstance(requirement.get("app"), dict) else {}
    app_name = str(app.get("name") or "").strip().lower()
    feature_titles = [_feature_title(item).lower() for item in _safe_features(requirement)[:3]]
    if app_name and app_name in lower and any(title and title in lower for title in feature_titles):
        return False
    # `placeholder` is also a normal Compose TextField parameter. Treating the
    # identifier itself as placeholder content incorrectly penalizes real forms.
    generic_markers = ("core feature", "sample app", "todo:", "lorem ipsum", "generated app")
    return any(marker in lower for marker in generic_markers)


def _store_asset_score(icon_path: Path, screenshots: list[str], metadata_root: Path) -> int:
    score = 100
    if not icon_path.is_file():
        score -= 25
    if len([p for p in screenshots if Path(p).is_file()]) < 1:
        score -= 35
    score -= _metadata_penalty(metadata_root)
    return int(_clamp_score(score))


def _metadata_penalty(metadata_root: Path) -> int:
    candidates = [metadata_root / "zh-CN", metadata_root]
    files = ("name.txt", "subtitle.txt", "description.txt", "keywords.txt")
    for root in candidates:
        if root.is_dir() and all((root / name).is_file() and (root / name).read_text(encoding="utf-8").strip() for name in files):
            return 0
    return 30


def _pain_topic_as_feature(requirement: dict[str, Any]) -> bool:
    for feature in _safe_features(requirement):
        title = _feature_title(feature).strip().lower()
        if title in PAIN_TOPIC_TITLES:
            return True
    return False


def _has_forbidden_scope(requirement: dict[str, Any], project_dir: Path) -> bool:
    scoped_requirement = {
        "app": requirement.get("app"),
        "features": requirement.get("features"),
        "core_logic": requirement.get("core_logic"),
        "ui_layout": requirement.get("ui_layout"),
        "store": requirement.get("store"),
    }
    req_text = json.dumps(scoped_requirement, ensure_ascii=False).lower()
    if _contains_positive_scope(req_text):
        return True
    src_root = project_dir / "app" / "src" / "main" / "java"
    files = list(src_root.rglob("*.kt")) if src_root.exists() else []
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in files[:8]).lower()
    return _contains_positive_scope(text)



def _contains_positive_scope(text: str) -> bool:
    """Detect requested scope while ignoring common negative constraints."""
    lower = text.lower()
    negations = ("no", "not", "without", "avoid", "exclude", "forbid", "无需", "不需要", "不含", "没有", "避免", "禁止")
    post_negations = ("not required", "is not required", "isn't required", "optional", "不需要", "无需")
    clause_boundaries = ".;:!?。；！？\n"
    for keyword in FORBIDDEN_SCOPE_KEYWORDS:
        pattern = re.escape(keyword)
        if keyword.isascii():
            pattern = rf"(?<![a-z0-9]){pattern}(?![a-z0-9])"
        for match in re.finditer(pattern, lower):
            index = match.start()
            clause_start = max(lower.rfind(mark, 0, index) for mark in clause_boundaries)
            prefix = re.sub(r"[\s_\-]+", " ", lower[clause_start + 1:index]).strip()
            suffix_start = index + len(keyword)
            suffix = re.sub(r"[\s_\-]+", " ", lower[suffix_start:suffix_start + 24]).strip()
            prefix_is_negated = any(token in prefix for token in negations)
            suffix_is_negated = any(suffix.startswith(token) for token in post_negations)
            if not prefix_is_negated and not suffix_is_negated:
                return True
    return False


def _find_tokens(text: str, token_map: dict[str, str]) -> list[str]:
    return [name for name, token in token_map.items() if token in text]


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _clamp_score(value: float | int) -> int:
    return int(max(0, min(100, round(float(value)))))

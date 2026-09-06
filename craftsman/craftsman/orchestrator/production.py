from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from craftsman.store.db import RunStore


@dataclass(frozen=True)
class ProductionStageSpec:
    key: str
    order: int
    label: str
    running_message: str


PRODUCTION_STAGES = (
    ProductionStageSpec("product_definition", 10, "整理产品方案", "正在明确用户、问题和首版范围"),
    ProductionStageSpec("experience_design", 20, "设计使用流程", "正在设计页面状态和操作路径"),
    ProductionStageSpec("core_build", 30, "制作核心功能", "正在完成最主要的使用闭环"),
    ProductionStageSpec("feature_expansion", 40, "完善功能", "正在补充首版所需功能"),
    ProductionStageSpec("product_polish", 50, "完善使用体验", "正在完善界面、文案和应用素材"),
    ProductionStageSpec("validation", 60, "检测并修复", "正在安装、检查并修复问题"),
    ProductionStageSpec("release_candidate", 70, "生成可发布版本", "正在整理预览和发布材料"),
)

_STAGES_BY_KEY = {stage.key: stage for stage in PRODUCTION_STAGES}


def stage_specs_payload() -> list[dict[str, Any]]:
    return [asdict(stage) for stage in PRODUCTION_STAGES]


def build_product_brief(requirement: dict[str, Any]) -> dict[str, Any]:
    app = requirement.get("app") if isinstance(requirement.get("app"), dict) else {}
    meta = (
        requirement.get("opportunity_meta")
        if isinstance(requirement.get("opportunity_meta"), dict)
        else {}
    )
    feature_names = []
    for feature in requirement.get("features") or []:
        if isinstance(feature, dict):
            name = feature.get("title") or feature.get("name") or feature.get("id")
        else:
            name = feature
        if name:
            feature_names.append(str(name))
    primary = feature_names[0] if feature_names else str(app.get("name") or "主要功能")
    return {
        "schema_version": 1,
        "app_name": app.get("name"),
        "target_users": meta.get("target_users") or "需要使用该工具的用户",
        "problem": meta.get("core_pain") or meta.get("competitor_gap") or primary,
        "primary_outcome": f"用户可以完成：{primary}",
        "core_features": feature_names[:3],
        "out_of_scope": ["登录与账号", "在线支付", "云端同步", "复杂后端服务"],
        "source_opportunity_id": requirement.get("opportunity_id"),
    }


def build_experience_spec(
    requirement: dict[str, Any], implementation_plan: dict[str, Any]
) -> dict[str, Any]:
    layout = requirement.get("ui_layout") if isinstance(requirement.get("ui_layout"), dict) else {}
    return {
        "schema_version": 1,
        "primary_user_flow": implementation_plan.get("primary_user_flow"),
        "screens": implementation_plan.get("screens") or layout.get("screens") or ["Main"],
        "screen_states": implementation_plan.get("screen_states") or {},
        "user_actions": implementation_plan.get("user_actions") or [],
        "acceptance_actions": implementation_plan.get("acceptance_actions") or [],
        "local_storage": implementation_plan.get("local_storage"),
    }


def write_json_artifact(workspace: Path, name: str, payload: dict[str, Any]) -> Path:
    target = workspace / name
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


class ProductionSession:
    """Persistent stage checkpoint record for one product-making run."""

    def __init__(self, store: RunStore, run_id: str, workspace: Path) -> None:
        self.store = store
        self.run_id = run_id
        self.workspace = workspace
        self.current_stage: str | None = None
        self.store.ensure_production_stages(run_id, stage_specs_payload())
        self._write_snapshot()

    def start(
        self,
        stage_key: str,
        *,
        inputs: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        spec = self._spec(stage_key)
        self.current_stage = stage_key
        self.store.start_production_stage(
            self.run_id,
            stage_key,
            user_message=message or spec.running_message,
            inputs=inputs or {},
        )
        self._write_snapshot()

    def complete(
        self,
        stage_key: str,
        *,
        outputs: dict[str, Any] | None = None,
        acceptance: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        spec = self._spec(stage_key)
        self.store.complete_production_stage(
            self.run_id,
            stage_key,
            user_message=message or f"{spec.label}已完成",
            outputs=outputs or {},
            acceptance=acceptance or {"passed": True},
        )
        if self.current_stage == stage_key:
            self.current_stage = None
        self._write_snapshot()

    def fail(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        if self.current_stage:
            self.store.fail_production_stage(
                self.run_id,
                self.current_stage,
                user_message=message,
                acceptance={"passed": False, **(details or {})},
            )
            self.current_stage = None
            self._write_snapshot()

    def _spec(self, stage_key: str) -> ProductionStageSpec:
        try:
            return _STAGES_BY_KEY[stage_key]
        except KeyError as exc:
            raise ValueError(f"unknown production stage: {stage_key}") from exc

    def _write_snapshot(self) -> None:
        payload = {
            "schema_version": 1,
            "run_id": self.run_id,
            "stages": self.store.list_production_stages(self.run_id),
        }
        write_json_artifact(self.workspace, "production_session.json", payload)

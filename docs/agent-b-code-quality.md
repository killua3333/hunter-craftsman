# Agent B 代码质量与可交付 MVP 标准

本文说明当前 Agent B 的目标、生成合约、质量评分和发布门槛。

## 当前目标

Agent B 的阶段目标不是“覆盖所有精品 App”，而是把任意合适需求收敛成一个真实可操作、可演示、可进入 internal track 的 Android MVP。

生成结果必须满足：

- Android 优先使用 Kotlin + Compose。
- 有明确首页、空状态、输入或操作状态、结果或列表状态。
- 至少有一个真实交互控件。
- 有本地状态；轻状态优先 `rememberSaveable`，需要持久化时使用 `SharedPreferences`。
- 不默认生成登录、订阅、支付、云同步、复杂后端依赖。
- 不把差评痛点如“广告多、崩溃、订阅贵”直接当作 App 功能。

## MVP 生成合约 v2

每次生成会写入 `implementation_plan.json`，核心字段包括：

- `schema_version = 2`
- `primary_user_flow`：一个主用户流程。
- `core_features`：最多 3 个核心功能。
- `screen_states`：首页、空状态、操作状态、结果状态等。
- `local_storage`：本地状态或持久化方式。
- `acceptance_actions`：人工或自动验收动作。
- `forbidden_scope`：本轮不允许扩展的复杂能力。

代码生成必须围绕这个计划执行。多轮修复时，第三轮会缩小范围到一个主功能，但不改变 App 类型。

## AppBuildQualityReport v2

质量报告保留旧字段并增加分项评分：

- `quality_score`：0-100 总分。
- `release_ready`：是否允许进入发布。
- `failure_classes`：失败类别，例如 `empty_ui`、`weak_core_flow`、`no_persistence`、`generic_template`、`poor_store_assets`、`build_failed`、`forbidden_scope`。
- `repair_suggestions`：修复建议。
- `core_flow_score`：主流程质量。
- `ui_completeness_score`：UI 状态完整性。
- `persistence_score`：本地状态或持久化证据。
- `store_asset_score`：图标、截图、metadata 等素材。
- `product_specificity_score`：是否贴合当前需求，而不是通用模板。
- `manual_review_notes`：给操作者看的判断说明。

## 发布门槛

- `quality_score >= 75` 且 `release_ready = true`：建议发布，可以进入 Agent C。
- `60 <= quality_score < 75`：可以预览，建议继续打磨，不自动发布。
- `quality_score < 60`：视为生成失败，进入修复或缩小范围。

Agent C 在提交前会再次检查质量门槛；低质量 handoff 会返回 `quality_gate_blocked`，并提示继续修复或人工确认。

## 自修复策略

最多 3 轮质量修复：

1. 修 UI 空白、无交互、无本地状态。
2. 修主流程弱、文案模板化、功能不贴合需求。
3. 缩小范围，只保留一个主功能。

每轮修复后都会重新构建、重新评分、重新写质量报告。

## 验收建议

交接或演示前至少检查：

- `implementation_plan.json` 是否存在且字段完整。
- Dashboard 生成进度是否显示质量分和建议。
- 生成 App 是否能看出真实主功能。
- 截图、图标、metadata 是否存在。
- 质量分低于 75 时是否被阻断在发布前。

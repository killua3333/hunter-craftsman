# Agent B v3 分阶段产品生产与质量标准

本文说明 Agent B 的固定产品生产流程、阶段检查点与重试、Coding Provider、质量评分和发布门槛。

## 固定产品生产流程

Agent B 不再把“生成一个 App”视为一次模型请求。每个 App 固定经过七个阶段：

1. `product_definition`：整理产品方案，明确用户、问题、核心结果和首版范围。
2. `experience_design`：设计使用流程、页面状态、操作路径和验收动作。
3. `core_build`：先完成一个端到端的核心功能闭环。
4. `feature_expansion`：在核心流程可用的基础上补充其余首版功能。
5. `product_polish`：完善界面、产品文案、边界状态和应用素材。
6. `validation`：编译、运行、质量检查并按具体问题修复。
7. `release_candidate`：整理 APK、预览、质量报告和 Agent C 交接材料。

用户界面只展示“整理产品方案、设计使用流程、制作核心功能、完善功能、完善使用体验、检测并修复、生成可发布版本”。模型、命令、源码路径和构建日志只出现在技术信息中。

## 持久化与重试

每个 run 在 SQLite 的 `production_stages` 表中保存：

- 阶段状态和顺序。
- 当前尝试次数。
- 阶段输入和输出。
- 验收结果。
- 用户可理解的进度说明。
- 开始、完成和更新时间。

工作区同时保存：

- `product_brief.json`
- `experience_spec.json`
- `implementation_plan.json`
- `production_session.json`
- `coding/*.prompt.txt`
- `coding/*.log`
- `coding/*.json`

进程或服务器中断后，可以从数据库和工作区判断已完成阶段及当前失败阶段。重新排队会继续使用同一个工程目录，重试阶段的 `attempt` 会递增，之前的阶段记录和产物会保留。目前编排器仍会重新检查部分前置步骤；“从首个未完成阶段自动续跑且完全跳过已完成步骤”属于后续增强，不在本版本中宣称完成。

## Coding Provider

默认 `CODING_PROVIDER=deepseek_json`，保持原有 DeepSeek JSON 文件生成兼容。

当配置为 `codex`、`claude` 或 `command` 时，Agent B 使用工作区型 Coding Harness。编码执行器会在同一个 Android 工程中依次处理核心功能、功能补充、体验完善和问题修复，而不是每轮返回一个全新工程。

执行边界：

- 工程目录必须位于当前 run 的 workspace 内。
- 使用参数数组启动进程，不经过 shell。
- 可执行文件必须位于 `CODING_AGENT_ALLOWED_EXECUTABLES` 白名单。
- 每轮有独立超时。
- Harness 不向编码命令传递 Agent C 的发布参数，提示词也明确禁止发布操作。
- 每轮提示词、输出日志和源码变更列表都会留存。

这里的目录和命令白名单是应用层约束，不等同于操作系统沙箱。生产部署时应使用独立低权限系统账号运行 Craftsman，并只向该账号提供编码 CLI 所需权限。

示例配置：

```dotenv
CODING_PROVIDER=codex
CODING_AGENT_COMMAND_JSON=["codex","exec","--full-auto","-"]
CODING_AGENT_ALLOWED_EXECUTABLES=codex,claude
CODING_AGENT_TIMEOUT_SECONDS=1800
```

CLI 必须提前安装，并由运行 Craftsman 的系统账号完成合法认证。命令参数应以服务器实际安装版本为准，启用前必须在测试环境跑基准任务。

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

## 当前边界与下一步

v3 当前已经完成固定七阶段、阶段持久化、失败重试记录、Dashboard/API 展示，以及 Codex/Claude 工作区执行器边界。现有 Gradle 构建和 Android 启动冒烟检查继续复用。

下一增量必须补齐真实设备级产品验收：

- 在 Android 模拟器或测试设备安装 APK。
- 使用 Maestro 或 UIAutomator 执行 `acceptance_actions`。
- 验证关闭并重启后的数据持久化。
- 保存真实 App 页面截图，而不是商店宣传图。
- 使用独立评审器检查遮挡、乱码、空页面和需求覆盖。
- 将失败步骤作为结构化缺陷交回 Coding Harness，修复后进行回归。

在上述设备级验收完成前，系统可以证明工程编译和基础启动，但不能仅凭源码特征宣称 App 已达到成熟商业产品质量。

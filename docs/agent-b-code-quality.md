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

推荐使用 `CODING_PROVIDER=deepseek_harness`：Agent B 通过 DeepSeek 官方 Python SDK 和随包运行时驱动官方 Harness，默认使用 `deepseek-v4-pro`。这不是项目自建的简化工具循环，也不是原有的一次性 JSON 生成。服务器安装项目依赖时会一并安装 Harness 运行时，平台用户无需安装 Codex、Node.js 或额外客户端。

`CODING_PROVIDER=deepseek_json` 仅保留原有 DeepSeek JSON 文件生成兼容。

当配置为 `deepseek_harness`、`codex_deepseek`、`codex`、`claude` 或 `command` 时，Agent B 使用工作区型 Coding Harness。编码执行器会在同一个 Android 工程中依次处理核心功能、功能补充、体验完善和问题修复，而不是每轮返回一个全新工程。

使用 DeepSeek 官方 Harness：

```dotenv
CODING_PROVIDER=deepseek_harness
DEEPSEEK_API_KEY=
DEEPSEEK_HARNESS_MODEL=deepseek-v4-pro
DEEPSEEK_HARNESS_REASONING_EFFORT=high
DEEPSEEK_HARNESS_MAX_TOKENS=49152
DEEPSEEK_HARNESS_PROFILE=sdk
```

项目固定使用完整 `sdk` profile，其默认权限为 `workspace-write`。不会使用官方 `sdk-minimal` profile，因为后者固定为 `danger-full-access`。Harness 在隔离的内部 Python 进程中运行，该进程只继承运行所需的系统变量、网络代理和 DeepSeek Key，不继承 Google Play、Android 签名或平台 API 凭据。遥测在该进程中明确关闭。

Android Gradle 构建容器同样不会挂载平台 `secrets` 目录。发布签名与 Google Play 上传仍由 Agent C 的受控发布阶段处理，不交给 Agent B 生成的工程或构建脚本。

DeepSeek Harness 当前仍由官方标记为开发者预览，版本可能发生不兼容变更，因此依赖固定为已验证的 `0.1.2rc1`。升级 SDK 前必须重新执行最小文件修改、Android 编译和完整回归测试。

备选方案：使用 DeepSeek 驱动 Codex Harness：

```dotenv
CODING_PROVIDER=codex_deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
CODEX_DEEPSEEK_MODEL=deepseek-v4-pro
CODEX_DEEPSEEK_REASONING_EFFORT=high
```

要求 Codex CLI 版本不低于 DeepSeek 模型目录声明的 `0.144.0`。项目使用 `--ignore-user-config` 和独立 Provider 参数，不读取或覆盖操作者桌面 Codex 的模型服务配置。DeepSeek Key 通过受限子进程环境注入，不写入命令参数和模型目录。Agent C 的 Play 与签名凭据不会传给 Codex。

执行边界：

- 工程目录必须位于当前 run 的 workspace 内。
- 每个 App 工程创建独立 Git 边界，避免编码工具向上扫描平台主仓库。
- 使用参数数组启动进程，不经过 shell。
- 可执行文件必须位于 `CODING_AGENT_ALLOWED_EXECUTABLES` 白名单。
- 每轮有独立超时。
- Harness 不向编码命令传递 Agent C 的发布参数，提示词也明确禁止发布操作。
- 每轮提示词、输出日志和源码变更列表都会留存。

这里的目录和命令白名单是应用层约束，不等同于操作系统沙箱。生产部署时应使用独立低权限系统账号运行 Craftsman，并只向该账号提供编码 CLI 所需权限。

示例配置：

```dotenv
CODING_PROVIDER=codex
CODING_AGENT_COMMAND_JSON=["codex","exec","--ephemeral","--sandbox","workspace-write","--skip-git-repo-check","-"]
CODING_AGENT_ALLOWED_EXECUTABLES=codex,claude
CODING_AGENT_TIMEOUT_SECONDS=1800
```

CLI 必须提前安装。通用 `codex`、`claude` Provider 需要由运行 Craftsman 的系统账号完成相应认证；`codex_deepseek` 只读取 DeepSeek API Key。命令参数应以服务器实际安装版本为准，启用前必须在测试环境跑基准任务。Codex 官方文档建议自动化任务显式使用 `--sandbox workspace-write`；`--full-auto` 仅保留为兼容参数，本项目不再把它作为推荐配置。

`codex_deepseek` 不要求登录 ChatGPT，但必须配置有效的 DeepSeek API Key。通用 `codex` Provider 仍按其实际 OpenAI或自定义服务完成认证。

编码阶段的标准输出和错误输出会持续写入当前 run 的 `coding/<stage>-<attempt>.log`。工作台只展示当前产品阶段和已运行时长，不展示虚构百分比。Codex Desktop 内再次启动 Codex CLI 可能受嵌套沙箱限制；生产验证应由普通终端或独立服务进程运行。

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

每轮修复后都会重新构建、重新执行设备启动检查、重新评分并写入质量报告。源码变化后不会沿用旧版本的设备证据。

## 验收建议

交接或演示前至少检查：

- `implementation_plan.json` 是否存在且字段完整。
- Dashboard 生成进度是否显示质量分和建议。
- 生成 App 是否能看出真实主功能。
- 截图、图标、metadata 是否存在。
- 质量分低于 75 时是否被阻断在发布前。

## 当前边界与下一步

v3 当前已经完成固定七阶段、阶段持久化、失败重试记录、Dashboard/API 展示、Codex/Claude 工作区执行器边界，以及 Android 编译与设备启动证据分离。商店宣传截图不会再被当成设备截图；没有设备启动证据的 Android 产物不能通过发布门槛。Linux 验证主机需要提供 `/dev/kvm`，Windows Docker Desktop 通常只能完成原生编译。

下一增量必须补齐核心业务流程级产品验收：

- 使用 Maestro 或 UIAutomator 执行 `acceptance_actions`。
- 验证关闭并重启后的数据持久化。
- 保存真实 App 页面截图，而不是商店宣传图。
- 使用独立评审器检查遮挡、乱码、空页面和需求覆盖。
- 将失败步骤作为结构化缺陷交回 Coding Harness，修复后进行回归。

当前系统可以分别证明工程编译和基础设备启动；在上述核心流程验收完成前，仍不能仅凭随机 smoke 或源码特征宣称 App 已达到成熟商业产品质量。

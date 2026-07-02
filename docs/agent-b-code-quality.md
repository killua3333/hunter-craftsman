# Agent B 代码质量策略

Agent B 负责把 requirement 转为 Android MVP。

## 生成约束

Android 优先 Kotlin + Compose。每个 App 必须有主功能、空状态或初始状态、交互控件和本地状态。禁止默认生成登录、订阅、云同步和复杂后端。

## 验收 gates

保留 Gradle 编译、smoke test 和产物检查。新增 UI 完整性检查：MainActivity 存在、包含 Compose setContent、至少一个交互控件、至少一个本地状态或持久化痕迹。

## 失败分类

空 UI 使用 `codegen_empty_ui`；构建失败使用 build failure taxonomy；产物缺失使用 hard gate failure。多次失败后缩小需求范围重试。

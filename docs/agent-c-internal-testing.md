# Agent C Google Play internal track 发布说明

本文说明当前 Agent C 的稳定发布模型。当前只承诺 Google Play `internal` 内部测试轨道，不做 production。

## 正确上架模型

Google Play Developer API 不能创建全新的 Play Console App。稳定模型是：

1. 人工在 Play Console 批量预创建 App 和包名。
2. 将这些包名写入 `.env` 的 `PACKAGE_POOL`。
3. Dashboard 点击“发布配置 -> 同步配置”。
4. Dashboard 点击“验证包名”，系统调用 Play API 检查包名是否存在、service account 是否有权限。
5. Agent B 只能从包名池分配可用包名。
6. Agent C 只对已存在且可访问的 App 上传 AAB 并提交 internal track。
7. 成功提交 internal 后，该包名永久占用。

## 包名池状态机

- `available`：在池中，尚未分配。
- `allocated`：已分配给某个生成任务。
- `verified`：Play API 已确认可访问。
- `invalid`：包名不存在、未授权或被人工标记无效。
- `released`：生成失败或未发布后释放，可重新使用。
- `submitted_internal`：已成功提交 internal，永久占用。

## Dashboard 管理入口

页面：“发布配置”。

可执行操作：

- 同步配置：从 `.env PACKAGE_POOL` 同步包名，不覆盖已有状态。
- 验证包名：调用 Play API 批量检查包名存在性和权限。
- 释放：人工释放未成功发布的包名。
- 标记无效：人工禁用不可用包名。

客户解释口径：

> 请先在 Play Console 批量创建这些 App，系统会自动检查并使用这些包名。

## 发布前强制检查

Agent C 提交前必须满足：

- Agent B `release_ready = true`。
- `quality_score >= 75`。
- 包名来自 `PACKAGE_POOL`。
- 包名未处于 `invalid` 或 `submitted_internal`。
- service account 可以创建 Play edit。
- signing、metadata、AAB、隐私政策 URL 均可用。

## 失败后的包名处理

- `package_not_precreated`：标记无效，释放当前 run 占用。
- `service_account_permission`：标记无效，释放当前 run 占用。
- `quality_gate_blocked`：默认释放包名，等待修复后重新生成或重新发布。
- `version_code_conflict`：保留占用，允许重试。
- `play_api_transient`：保留占用，稍后重试。
- `internal_submitted`：永久占用，不再释放。

## 常见失败类别

| failure_class | 含义 | 处理方式 |
| --- | --- | --- |
| `quality_gate_blocked` | App 质量分未达发布门槛 | 回到生成进度，继续修复或人工确认 |
| `package_not_from_pool` | 包名不是系统包名池分配 | 同步包名池，重新生成 |
| `package_not_precreated` | Play Console 未预创建该包名 | 先创建 App，再验证包名 |
| `service_account_permission` | service account 无权限 | 在 Play Console 授权 |
| `version_code_conflict` | versionCode 已使用 | 提高 versionCode 后重试 |
| `signing_config` | 签名配置错误 | 检查 keystore 和密码 |
| `metadata_incomplete` | 商店资料不完整 | 补齐 title、description、截图、图标 |
| `play_api_transient` | Google API 或网络临时失败 | 保留包名并稍后重试 |

## 验收标准

- 配置齐全时，系统可以真实上传 AAB 到 Google Play internal track。
- 包名池为空时，前端提示先配置包名池。
- 包名未预创建或无权限时，前端显示明确人工动作。
- 质量分低于 75 时不会进入真实上传。
- 真实上传成功后状态进入 `internal_submitted`，包名变为 `submitted_internal`。

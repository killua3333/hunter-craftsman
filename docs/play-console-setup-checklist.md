# Google Play internal track 配置清单

本文说明真实上传到 Google Play 内部测试轨道前必须完成的配置。

## 关键事实

Google Play Developer API 不能自动创建一个全新的 Play Console App。系统只能对已经存在、并且 service account 有权限访问的 App 执行上传、metadata 更新和 internal track 发布。

因此，稳定自动化的正确模型是：

1. 人工在 Play Console 批量预创建 App。
2. 将这些 App 的包名放入 `PACKAGE_POOL`。
3. 系统从包名池分配包名。
4. 发布前检查该包名是否可被 Play API 访问。
5. 成功提交 internal 后，包名永久占用。

## 1. Play Console 账号

确认已经完成：

- 注册 Google Play Developer 账号。
- 完成身份验证和付款。
- 能打开 [Play Console](https://play.google.com/console)。

## 2. Service Account

在 Google Cloud Console：

1. 打开 IAM / Service Accounts。
2. 创建 service account。
3. 创建 JSON key。
4. 下载为 `play-sa.json`。

在 Play Console：

1. 打开 Users and permissions。
2. 邀请 service account 邮箱。
3. 至少授予这些权限：
   - 查看 App 信息
   - 管理测试轨道
   - 发布到测试轨道
4. 如果是全局包名池，建议给全部预创建 App 授权。

本地放置：

```text
craftsman/secrets/play-sa.json
```

`.env` 配置：

```env
GOOGLE_PLAY_SERVICE_ACCOUNT_FILE=./secrets/play-sa.json
```

## 3. 签名 keystore

生成 keystore：

```powershell
keytool -genkeypair -v -storetype JKS -keyalg RSA -keysize 2048 -validity 10000 -alias release -keystore craftsman/secrets/release.jks
```

`.env` 配置：

```env
ANDROID_KEYSTORE_PATH=./secrets/release.jks
ANDROID_KEYSTORE_PASSWORD=...
ANDROID_KEY_ALIAS=release
ANDROID_KEY_PASSWORD=...
```

注意：keystore 必须备份。丢失后，已发布包名无法继续用同一签名更新。

## 4. 包名池

在 Play Console 逐个创建 App，并为每个 App 设置唯一包名，例如：

```text
com.yourbrand.template001
com.yourbrand.template002
com.yourbrand.template003
```

写入 `.env`：

```env
PACKAGE_POOL=com.yourbrand.template001,com.yourbrand.template002,com.yourbrand.template003
```

建议：

- 一次性准备 20 到 50 个包名。
- 不要把未创建或未授权的包名放入池子。
- 发布失败如果是 `package_not_precreated`，先处理 Play Console，而不是重试代码。

## 5. Android 构建环境

本地 Android SDK：

```env
ANDROID_BUILD_BACKEND=local
ANDROID_HOME=C:\Users\Administrator\AppData\Local\Android\Sdk
ANDROID_SDK_ROOT=C:\Users\Administrator\AppData\Local\Android\Sdk
```

或使用 Docker builder：

```env
ANDROID_BUILD_BACKEND=auto
```

## 6. 发布轨道
当前产品流程只支持真实上传到 Google Play internal track：

```env
ANDROID_RELEASE_TRACK=internal
```
## 7. 常见失败

| failure_class | 含义 | 处理 |
| --- | --- | --- |
| `package_not_precreated` | 包名没有在 Play Console 创建，或 service account 看不到 | 预创建 App，检查权限 |
| `service_account_permission` | service account 权限不足 | 在 Play Console 授权测试轨道发布权限 |
| `version_code_conflict` | versionCode 已经用过 | 提高 versionCode 后重试 |
| `signing_config` | keystore 或密码错误 | 检查签名配置 |
| `metadata_incomplete` | 商店素材或隐私 URL 不完整 | 补齐 metadata、图标、截图、隐私政策 |
| `play_api_transient` | Google API 临时失败或网络超时 | 保留包名，稍后重试 |
| `internal_track_unavailable` | internal track 配置不可用 | 在 Play Console 初始化内部测试轨道 |

## 8. 验收标准

配置完成后，应能做到：

1. Dashboard 能准备 release。
2. 发布前检查能识别包名、签名、metadata、service account。
4. 真实上传进入 `uploading_internal`。
5. 成功后状态为 `internal_submitted`。
6. 失败时能给出明确 failure_class 和人工处理建议。
## Dashboard 包名池验收

配置好 `.env PACKAGE_POOL` 后，在 Dashboard 执行：

1. 打开“发布配置”。
2. 点击“同步配置”。
3. 点击“验证包名”。
4. 确认可用包名数量大于 0。
5. 确认无效包名都有明确原因。

状态解释：

| 状态 | 含义 | 下一步 |
| --- | --- | --- |
| `available` | 已在池中，尚未分配 | 可用于后续生成 |
| `verified` | Play API 已确认可访问 | 优先使用 |
| `allocated` | 已分配给某个任务 | 等待生成或发布完成 |
| `released` | 失败后释放回池 | 可重新使用 |
| `invalid` | 包名不存在或无权限 | 处理 Play Console 后重新验证 |
| `submitted_internal` | 已成功提交 internal | 永久占用 |

如果真实上传失败：

- `package_not_precreated`：不要重试代码，先在 Play Console 创建 App。
- `service_account_permission`：不要更换代码，先给 service account 授权。
- `version_code_conflict`：保留包名，提高 versionCode 后重试。
- `play_api_transient`：保留包名，稍后重试。

## 9. 2026-07-03 验证记录与解释

已验证成功案例：

```text
Play Console App：AEM Template 002
包名：com.AEM.template002
系统生成 App：Checklist App MVP
发布轨道：internal testing
Play Console 显示：已面向内部测试人员发布
versionName：1.0.1
versionCode：3
```

### 创建 App 时的包名

当前 Play Console 创建应用页面可以直接填写“软件包名称”。这里填写的就是系统包名池里的包名，例如：

```text
com.AEM.template003
```

如果创建页显示“软件包名称可用”，说明这个包名可用于创建新的 Play Console App。创建后还必须给 service account 该 App 的权限，否则系统验证会失败。

### 包名状态说明

| 状态 | 解释 | 是否可用于新 App |
| --- | --- | --- |
| `verified` / `available` | Play Console 已创建且权限正常，尚未使用 | 可以 |
| `allocated` | 已被某个生成任务占用 | 暂时不可以 |
| `submitted_internal` | 已成功提交 internal testing | 不可以，永久占用 |
| `invalid` | 未创建或权限不足 | 不可以，先处理 Play Console |

### 同步配置与验证包名

- 同步配置：读取 `.env PACKAGE_POOL`，把包名名单导入系统。
- 验证包名：调用 Google Play API，确认包名对应的 App 是否存在、service account 是否有权限。

如果包名池显示 `available = 0`，不能继续自动发布新的 App。需要先在 Play Console 创建并授权下一个包名。

### 商店素材和 AAB 的关系

AAB 上传成功后，internal testing 版本可以发布。商店素材同步是另一层能力：名称、描述、截图、图标可能因为 Play Console 状态或素材规则失败。

当前系统策略是：如果素材同步失败，会重试只上传 AAB 到 internal track，以优先保证测试版本可见。此时 Play Console 能看到新版本，但 App 名称/描述/截图可能仍是预创建 App 的旧内容。

验收时需要区分：

1. internal testing 发布成功：看 Play Console 轨道和版本。
2. 生成 App 内容是否可用：看本地截图、APK 或通过测试链接安装。
3. 商店素材是否同步：看 Play Console store listing 是否更新。

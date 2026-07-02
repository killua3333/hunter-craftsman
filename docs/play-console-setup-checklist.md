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

## 6. 发布开关

演练模式：

```env
PUBLISHER_DRY_RUN=true
ANDROID_RELEASE_TRACK=internal
```

真实上传：

```env
PUBLISHER_DRY_RUN=false
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
3. dry-run 返回 `dry_run_complete`。
4. 真实上传进入 `uploading_internal`。
5. 成功后状态为 `internal_submitted`。
6. 失败时能给出明确 failure_class 和人工处理建议。
# Google Play 真上架配置清单

首次打通 internal track 真上架时，按本清单准备。完成后日常只需：

```powershell
hunter autopilot --publish
```

或手动描述：`hunter run "..." --publish`。

> **Master Roadmap 用户待办**：本节 P0 配置对应计划项 `user-play-secrets`；代码侧 Agent C 已就绪，密钥由你本地配置。

## P0 — 账号级（所有 app 共用，做一次）

### 1. Google Play 开发者账号

- 注册并完成身份验证与付款
- 确保能登录 [Play Console](https://play.google.com/console)

### 2. GCP Service Account + Play API 授权

1. 打开 [Google Cloud Console](https://console.cloud.google.com/) → IAM → Service Accounts
2. 创建 Service Account → 创建 JSON 密钥 → 下载 `play-sa.json`
3. 打开 Play Console → **Users and permissions** → **Invite new users**
4. 填入 Service Account 邮箱（形如 `xxx@xxx.iam.gserviceaccount.com`）
5. 角色选 **Admin** 或至少 **Release manager**
6. 勾选 **View app information**、**Manage testing tracks**、**Release to testing tracks**

放置密钥：

```text
craftsman/secrets/play-sa.json
```

在 [`craftsman/.env`](../craftsman/.env) 配置：

```env
GOOGLE_PLAY_SERVICE_ACCOUNT_FILE=./secrets/play-sa.json
```

### 3. Release Keystore

生成（仅一次，务必备份 `.jks` 和密码）：

```powershell
keytool -genkeypair -v -storetype JKS -keyalg RSA -keysize 2048 -validity 10000 ^
  -alias release -keystore craftsman/secrets/release.jks
```

在 `.env` 或 `craftsman/secrets/` 文件：

```env
ANDROID_KEYSTORE_PATH=./secrets/release.jks
ANDROID_KEYSTORE_PASSWORD=你的密码
ANDROID_KEY_ALIAS=release
ANDROID_KEY_PASSWORD=你的密码
```

### 4. Windows 构建环境（二选一）

**推荐：Docker builder（无需本机 SDK）**

| 组件 | 要求 |
|------|------|
| Docker Desktop | 运行 `hunter-craftsman/android-builder` 镜像 |
| `.env` | `ANDROID_BUILD_BACKEND=auto`，`SKIP_GRADLE_BUILD=false` |

见 [docker-android-ci.md](docker-android-ci.md)。

**备选：本机 SDK**

| 组件 | 要求 |
|------|------|
| JDK | 17+，设置 `JAVA_HOME` |
| Android SDK | build-tools 34+，`platforms;android-34` |
| 环境变量 | `ANDROID_HOME` 指向 SDK 根目录 |
| `.env` | `ANDROID_BUILD_BACKEND=local` |

### 5. Agent A / B 密钥

[`hunter/.env`](../hunter/.env)：

```env
DEEPSEEK_API_KEY=...
TAVILY_API_KEY=...
CRAFTSMAN_API_TOKEN=...    # 与 Craftsman API_TOKEN 一致
```

[`craftsman/.env`](../craftsman/.env)：

```env
DEEPSEEK_API_KEY=...
API_TOKEN=...
PUBLISHER_DRY_RUN=false
ANDROID_RELEASE_TRACK=internal
RELEASE_REQUIRE_HUMAN_APPROVAL=false
```

安装 Play 上传依赖：

```powershell
cd craftsman
pip install -e ".[publish]"
```

---

## P1 — 每个新 app（包名级，做一次）

### 0. 自动生成的操作清单（Agent C）

每次 `hunter autopilot --publish` 或 Agent C submit 时，系统会在工作区写入：

```text
workspace/{run_id}/play_console_setup.txt
workspace/{run_id}/play_console_setup.json
```

终端也会打印 **Play Console 操作清单**摘要（包名、应用名、描述、图标/截图路径、隐私 URL、问卷勾选建议）。  
预计人工操作约 **15 分钟**。本节 P1 步骤与清单内容一致，可按清单逐项完成。

### 1. 在 Play Console 创建应用

- **包名必须与 Agent A 输出的 `application_id` 完全一致**
- Google API **无法**自动创建 app，必须手动创建

建议包名格式：`com.yourbrand.appname`

### 2. 完成 Console 必填问卷

每个 app 需填写（否则 API 上传可能被拒）：

- 数据安全表单（Data safety）
- 内容分级（Content rating）
- 目标受众（Target audience）
- 隐私政策 URL（必须 HTTPS 可访问）

Agent B 会将占位 URL 部署到 Cloudflare Pages（`*.pages.dev`），见 [cloudflare-privacy-setup.md](cloudflare-privacy-setup.md)。  
清单中的 `privacy_url` 与 handoff 一致，可直接复制到 Console。

### 3. Internal 测试员

Play Console → **Testing** → **Internal testing** → **Testers**

- 添加测试员 Gmail 列表
- 测试员通过 Play 商店链接安装

---

## P2 — 日常自动化（无需人工）

配置完成后，每次新版本：

```powershell
# Terminal 1
cd craftsman
python -m craftsman.cli serve

# Terminal 2
cd hunter
hunter run "做一个离线番茄钟" --publish
```

Agent C 自动完成：

- versionCode 递增（对比 Play internal track 与本地）
- Gradle `bundleRelease` 打 signed AAB
- 同步商店文案（`play/metadata/zh-CN/`）
- 上传图标与截图（若产物存在）
- Play Edits API 上传并发布到 **internal** track

---

## 仍须人工的环节

| 环节 | 原因 |
|------|------|
| 首次 Console 创建 app | Google API 限制 |
| 数据安全 / 内容分级问卷 | 合规责任 |
| Keystore 备份与保管 | 丢失无法更新同包名 |
| Internal 测试员 Gmail 维护 | 首次需在 Console 添加 |
| Production 发布与政策审核 | 建议保留人工审批 |
| 复杂 app 编译失败 | 需调整需求或代码 |

---

## 验收标准

1. `PUBLISHER_DRY_RUN=false`，SA + keystore + SDK 就绪
2. Console 已创建 app，包名与 run 输出一致
3. `hunter run "..." --publish` 返回 `agent_c_status=submitted`
4. Play Console → Internal testing 可见新 `versionCode`
5. 测试员 Gmail 可在 Play 安装

---

## 推荐 secrets 目录结构

```text
craftsman/
  .env
  secrets/
    play-sa.json              # 勿提交 git
    release.jks               # 勿提交 git
    ANDROID_KEYSTORE_PASSWORD # 可选 file provider
hunter/
  .env
```

参考：[`craftsman/.env.example`](../craftsman/.env.example)

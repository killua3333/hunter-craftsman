# Hunter-Craftsman 从头到尾操作指导书

这份文档只讲真实流程，不讲演示兜底，不讲 dry-run。目标是：

- 点击一次后，系统自动完成真实需求发现。
- 人工从候选池里选中一个方向。
- 系统自动生成 Android App，做质量检查。
- 达标后，系统把 AAB 真实上传到 Google Play Console 的 internal testing 轨道。

## 1. 你先要知道的三件事

1. Agent A 负责找真实需求。
2. Agent B 负责把需求变成可运行的 Android MVP。
3. Agent C 负责把达标产物真实上传到 Google Play internal testing。

人类主要做两件事：

- 一次性把 Google Play、service account、签名、包名池配好。
- 运行时盯着 Dashboard，看结果、处理失败、必要时人工确认。

## 2. 一次性准备

### 2.1 Play Console 先准备好 App

Google Play 不允许系统直接创建一个全新的 Play Console App，所以你必须先人工准备好包名。

你需要做的事：

1. 登录 Google Play Console。
2. 预创建一批 App。
3. 每个 App 都要有唯一包名。
4. 把这些包名写进 `PACKAGE_POOL`。
5. 确保 service account 对这些 App 有发布权限。

建议包名示例：

```env
PACKAGE_POOL=com.yourbrand.template001,com.yourbrand.template002,com.yourbrand.template003
```

### 2.2 service account

把 Google Cloud 里创建好的 service account JSON 放到：

```text
craftsman/secrets/play-sa.json
```

`.env` 里要有：

```env
GOOGLE_PLAY_SERVICE_ACCOUNT_FILE=./secrets/play-sa.json
```

### 2.3 签名配置

你还需要准备 Android keystore：

```env
ANDROID_KEYSTORE_PATH=./secrets/release.jks
ANDROID_KEYSTORE_PASSWORD=...
ANDROID_KEY_ALIAS=release
ANDROID_KEY_PASSWORD=...
```

### 2.4 网络代理

如果当前服务器访问 Google Play / Google Publisher API / Tavily 需要代理，请先设置实际可用的代理地址；如果服务器可直连外网，则这一步可以跳过：

```powershell
$env:HTTP_PROXY="http://<your-proxy-host>:<your-proxy-port>"
$env:HTTPS_PROXY="http://<your-proxy-host>:<your-proxy-port>"
```

这里的代理端口只用于服务器本机出网，不是需要对外开放的访问端口。

### 2.5 `.env` 基础配置

先复制模板：

```powershell
cd D:\A\hunter-craftsman\craftsman
copy .env.example .env
```

然后确认至少有这些项：

- `DEEPSEEK_API_KEY`
- `ANDROID_RELEASE_TRACK=internal`
- `GOOGLE_PLAY_SERVICE_ACCOUNT_FILE`
- `ANDROID_KEYSTORE_PATH`
- `PACKAGE_POOL`

## 3. 启动前后端

### 3.1 安装依赖

```powershell
cd D:\A\hunter-craftsman\craftsman
pip install -e ".[dev,publish]"
```

### 3.2 启动 Dashboard

```powershell
cd D:\A\hunter-craftsman\craftsman
$env:PYTHONPATH="D:\A\hunter-craftsman\hunter\src;D:\A\hunter-craftsman\craftsman"
python .\scripts\serve_dashboard.py
```

打开：

- `http://127.0.0.1:8791/dashboard`
- `http://127.0.0.1:8791/health`

### 3.3 启动后先看什么

先确认三件事：

- `health` 是正常的。
- Dashboard 能打开。
- 页面里没有明显报错。

## 4. 正常工作流

### 第 1 步：开始真实需求发现

在 Dashboard 的“机会发现”页点击开始。

这一步系统会做：

1. 生成搜索方向。
2. 搜索 Google Play。
3. 扫竞品详情。
4. 抓低分评论。
5. 聚合痛点。
6. 生成候选需求。

你要看的是：

- 当前阶段是否在推进。
- 有没有真实搜索词。
- 有没有竞品和评论证据。
- 有没有候选进入需求池。

### 第 2 步：人工挑一个候选

进入“需求池”页，看每个候选的：

- App 名称
- 细分领域
- 目标用户
- 痛点摘要
- 来源 App
- 证据强度
- 机会分
- 适配分

你要做的是：

- 选一个最像真实产品机会的候选。
- 不要选证据太弱、太空、太泛的方向。
- 默认是人工确认后再进入生成。

### 第 3 步：开始代码生成

点击“进入生成”后，系统会：

1. 生成 `implementation_plan.json`。
2. 生成 Android 代码。
3. 编译。
4. 跑质量检查。
5. 产出质量报告。

你要看的是：

- 是否有主页面。
- 是否有交互控件。
- 是否有本地状态。
- 质量分是否达到发布门槛。

### 第 4 步：质量达标后自动准备发布

质量通过后，系统会自动进入发布准备：

- 选包名池里的包名。
- 检查签名。
- 检查 metadata。
- 检查 Play 权限。
- 构建 AAB。

### 第 5 步：真实上传到 Google Play internal testing

这一部是真实上传，不是模拟。

系统会把产物上传到：

- Google Play Console
- 对应 App 的 `Internal testing` 轨道

上传动作通常是通过 Google Play Android Publisher API 的 edits 流程完成的：

1. 创建 edit。
2. 上传 AAB。
3. 写入商店素材。
4. 设置 internal testing 轨道。
5. commit 提交。

如果成功，Dashboard 会显示：

- `uploading_internal`
- `internal_submitted`

这表示已经进到 Play Console 的 internal testing 里了。

## 5. 人类在自动上传里要做什么

### 你需要做的

- 预先创建 Play Console App。
- 把包名放进 `PACKAGE_POOL`。
- 配好 service account。
- 配好 keystore。
- 确保 release track 是 `internal`。
- 发现失败时按提示修权限、包名或素材。

### 你不需要每次做的

- 不需要手工打包 APK。
- 不需要手工上传 AAB。
- 不需要每次手工填 metadata。
- 不需要每次手工去 Play Console 点发布。

### 上传是传到哪里

上传目标只有一个：

- Google Play Console 里那个已经预创建好的 App
- 它的 `Internal testing` 轨道

不是传到别的服务器，也不是传到本地目录。

## 6. 录演示视频时怎么讲

建议按这个顺序演示：

1. 打开 Dashboard。
2. 先看“机会发现”。
3. 点击开始发现，展示阶段变化。
4. 进入“需求池”，展示候选、证据和评分。
5. 选择一个候选进入生成。
6. 展示生成进度和质量分。
7. 展示发布配置里的包名池。
8. 展示最终提交到 internal testing。

## 7. 常见失败和处理

### 7.1 发现失败

常见原因：

- 代理没配好。
- 搜索词太窄。
- Google Play 请求失败。
- 评论证据太少。

处理：

- 检查代理。
- 换更宽的搜索词。
- 保留失败，不要造结果。

### 7.2 生成失败

常见原因：

- 代码没编过。
- UI 太空。
- 没有交互控件。
- 没有本地状态。
- 质量分太低。

处理：

- 先看质量报告。
- 再看 build log。
- 必要时缩小功能范围。

### 7.3 发布失败

常见原因：

- 包名没在 Play Console 预创建。
- service account 没权限。
- versionCode 冲突。
- metadata 不完整。
- Play API 临时失败。

处理：

- `package_not_precreated`：先去 Play Console 创建 App。
- `service_account_permission`：先补权限。
- `version_code_conflict`：提高 versionCode 后重试。
- `play_api_transient`：稍后重试。

## 8. 你可以直接照着做的一套最短流程

```powershell
cd D:\A\hunter-craftsman\craftsman
copy .env.example .env
# 只有当前服务器访问 Google / Tavily 必须经过代理时，才需要设置下面两行
$env:HTTP_PROXY="http://<your-proxy-host>:<your-proxy-port>"
$env:HTTPS_PROXY="http://<your-proxy-host>:<your-proxy-port>"
$env:PYTHONPATH="D:\A\hunter-craftsman\hunter\src;D:\A\hunter-craftsman\craftsman"
python .\scripts\serve_dashboard.py
```

然后在浏览器里：

1. 打开 Dashboard。
2. 启动机会发现。
3. 选一个候选。
4. 进入生成。
5. 等待自动上传 internal testing。

## 9. 一句话总结

这套系统的真实闭环就是：

**Google Play 找机会 -> 人工选候选 -> 自动生成 App -> 自动质量检查 -> 自动上传到 Play internal testing**

## 10. 跑完后怎么确认

一轮完整流程成功后，至少确认三处：

1. Dashboard 生成进度显示质量分 `>= 75`，并且发布阶段为“已提交测试”。
2. Google Play Console -> 对应 App -> Internal testing 显示新版本已发布给内部测试人员。
3. 本地 `workspace/<run_id>/artifacts/screenshots/` 有生成截图，`artifacts/app-release.aab` 存在。

2026-07-03 已跑通的参考记录：

```text
App 方向：checklist app
生成 App：Checklist App MVP
包名：com.AEM.template002
run_id：4aa416a6-181e-4b10-95c4-c584f03cf485
release_id：rel-4aa416a6-181e-4b10-95c4-c584f03cf485
Play Console：internal testing 已发布
versionName：1.0.1
versionCode：3
```

## 11. 怎么看生成 App 的真实内容

Google Play Console 只能证明发布状态，不能像手机一样展示 App 的真实交互界面。

要看 App 长什么样：

1. 在 Dashboard 的“生成进度”查看 App 名称、质量分和发布状态。
2. 打开本地生成截图：

```text
craftsman/workspace/<run_id>/artifacts/screenshots/
```

3. 安装 APK 到手机或模拟器：

```text
craftsman/workspace/<run_id>/artifacts/app-debug.apk
```

4. 或者用内部测试账号从 Google Play 安装 internal testing 版本。

如果 Play Console 里仍显示 `AEM Template 002` 这类名称，而不是生成 App 名称，通常是因为这次只上传了 AAB，商店素材没有同步成功。发布链路仍然可以成功，但产品展示素材需要后续补同步或手动更新。

## 12. 包名池用完怎么办

每个新 App 都需要一个新的 Play Console 包名。已经提交 internal 的包名不能再作为新 App 使用。

如果 Dashboard 显示：

```text
可用包名：0
需要处理：18
```

说明当前没有可用于新发布的包名。下一轮前需要：

1. 在 Play Console 创建新 App，例如 `AEM Template 003`。
2. 软件包名称填写 `com.AEM.template003`。
3. 给 service account 授权该 App。
4. 回 Dashboard 点击“同步配置”。
5. 点击“验证包名”。
6. 等可用包名变成 `1` 后再开始下一轮。

“同步配置”只是导入 `.env PACKAGE_POOL` 名单；“验证包名”才会连接 Google Play 检查这个包名是否真的能发布。

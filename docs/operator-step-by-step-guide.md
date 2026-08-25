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

角色分工：

- 普通用户：只需要打开 Dashboard，填写关注方向、查看候选和进度。
- 系统管理员：负责 Google Play、Google Cloud、service account、签名、包名池、模型密钥和服务器环境。
- 应用负责人：确认生成 App 的真实质量，以及 Play Console 中由人承担责任的合规声明。

已经部署好的云端环境不需要普通用户再次启动 Hunter、Docker 或 Android 构建命令。Craftsman 服务会在后台调用这些能力。

### 1.1 哪些工作只做一次

以下配置对同一套服务器、同一个 Google Cloud 项目长期有效，不需要每发布一个 App 都重复操作：

1. 注册并完成 Google Play 开发者账号身份和付款验证。
2. 创建 Google Cloud 项目和 service account。
3. 在该 Google Cloud 项目启用 **Google Play Android Developer API**（`androidpublisher.googleapis.com`）。
4. 把 service account 加入 Play Console，并授予测试轨道和商店资料权限。
5. 配置并备份 Android keystore。
6. 配置模型 API Key、Dashboard `API_TOKEN`、Android SDK 或 Docker 构建环境。
7. 配置真实公网隐私政策地址、联系邮箱和 HTTPS 域名。
8. 仅在服务器无法直连 Google Play 时配置真实可用的出网代理。

### 1.2 每新增一个 Play App 都要做

Google Play Developer API 不能创建全新的 Play Console App。每增加一个可发布包名，管理员必须：

1. 在 Play Console 点击“创建应用”，创建真正的 App，而不是只在 `.env` 写一个包名字符串。
2. 为 App 设置唯一包名。
3. 如果 service account 不是全账号授权，为这个新 App 单独授予权限。
4. 把同一个包名加入 `.env` 的 `PACKAGE_POOL`。
5. 在 Dashboard“发布配置”依次点击“同步配置”和“验证包名”。
6. 看到“Play 可访问”后，才能交给 Agent B/C 使用。

### 1.3 每次生成和发布都要确认

1. 候选需求确实值得做，来源证据与建议功能没有明显偏差。
2. 生成 App 可以安装和操作，质量分不代替人工产品验收。
3. 隐私政策描述与 App 实际行为一致。
4. 内部测试成功后，在 Play Console 确认版本、包名和测试轨道正确。
5. 进入封闭测试或正式发布前，人工完成数据安全、内容分级、目标受众、广告、App 访问权限和测试人员等官方配置。

## 2. 一次性准备

### 2.1 Play Console 先准备好 App

Google Play 不允许系统通过 Android Publisher API 创建一个全新的 Play Console App，所以必须先人工创建真正的 App，并为它设置包名。只把包名写入 `.env` 不会创建 Play App。

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

先在 service account 所属 Google Cloud 项目执行一次：

1. 打开“API 和服务 -> API 库”。
2. 搜索并启用 **Google Play Android Developer API**。
3. 等待数分钟后再验证包名。

这是 Google Cloud 项目级开关。只要继续使用同一个项目，启用一次即可；新建 App、新增包名或更换同项目内的 service account 都不需要重复启用。只有更换 Google Cloud 项目、API 被人工关闭或项目被停用时才需要重新处理。

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
- `PRIVACY_POLICY_URL`
- `PRIVACY_CONTACT_EMAIL`
- `API_TOKEN`

隐私政策说明：

- 当前云端公共地址是 `https://hcapply.npzsk.com.cn/privacy`。
- 该地址不是只绑定某一个包名，而是供当前开发者账号下符合声明的本地工具 App 共用。
- 只要 App 仍然是本地存储、无账号、无广告、无分析 SDK、无支付和云同步，就可以持续使用。
- 如果未来 App 增加联网、登录、广告、分析、支付、订阅或云同步，必须先更新隐私政策和 Play 数据安全声明。
- 正式运营应使用项目专用联系邮箱；当前测试邮箱不应作为长期商业联系地址。

### 2.6 当前甲方云端已经完成的配置

截至 2026-08-26，当前服务器已经完成：

- Google Cloud 项目 `288325624096` 已启用 Google Play Android Developer API。
- service account 凭据可以访问 Android Publisher API。
- `com.hcap01.app` 至 `com.hcap05.app` 已通过 Play edit 和 internal 轨道读写验证。
- 公网隐私政策 `https://hcapply.npzsk.com.cn/privacy` 可以访问。
- Android release signing 已通过发布前检查。

因此，在继续使用当前 Google Cloud 项目和当前服务器配置时，甲方不需要为每个 App 重复启用 API。但以下变化仍需要管理员处理：

- 包名池用完：在 Play Console 创建新 App、设置新包名、授权并加入 `PACKAGE_POOL`。
- 换到新的 Google Cloud 项目：新项目必须重新启用 Android Publisher API。
- 更换 service account：替换 JSON；如果不是全账号授权，还要在 Play Console 授权。
- API 被关闭、项目停用或权限被收回：按 Dashboard 的真实错误重新处理。
- App 功能超出当前隐私政策范围：更新隐私政策和数据安全声明。

## 3. 启动前后端

甲方云端已经由 `craftsman.service` 常驻运行，普通用户跳过 3.1 和 3.2，直接打开：

- `https://hcapply.npzsk.com.cn/dashboard`
- `https://hcapply.npzsk.com.cn/health`

下面的安装和启动命令只用于首次部署或本地开发。

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

在 Dashboard 的“找机会”页填写关注方向，模式选择“一键自动生成并上架”，然后点击右上角同名按钮。

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

### 第 2 步：系统选择或人工挑一个候选

达到自动门槛时，系统会选一个候选进入生成；未达到时会停在“等待选择”。这时进入“可做的 App”页，看每个候选的：

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
- 点击“选择这个需求”后进入生成。只要本轮最初选择的是“一键自动生成并上架”，人工选择候选后仍会保留自动发布意图。

### 第 3 步：开始代码生成

自动选择成功或点击“选择这个需求”后，系统会：

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
- 检查隐私政策 URL 是否真实可访问并且不是占位地址。
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

- 管理员预先创建 Play Console App，并设置对应包名。
- 管理员把包名加入 `PACKAGE_POOL`，同步并验证。
- 管理员一次性启用 Android Publisher API、配置 service account、keystore 和隐私政策。
- 应用负责人安装并检查生成 App，确认隐私政策与实际行为一致。
- 发现失败时按页面提示处理权限、包名、素材或网络问题。

### 你不需要每次做的

- 不需要手工打包 APK。
- 不需要手工上传 AAB。
- internal 自动流程正常时，不需要每次手工填写名称、描述、图标和截图；上传后仍应在 Console 检查结果。
- 不需要每次手工去 Play Console 点发布。

### 上传是传到哪里

上传目标只有一个：

- Google Play Console 里那个已经预创建好的 App
- 它的 `Internal testing` 轨道

不是传到别的服务器，也不是传到本地目录。

### internal 之后仍需人工完成什么

当前自动化目标是 Google Play `internal` 内部测试，不等于封闭测试或正式公开发布。进入更高轨道前，应用负责人仍需在 Play Console 完成并确认：

- 数据安全声明：是否收集、共享、加密或删除用户数据。
- 内容分级问卷。
- 目标受众和儿童政策。
- 是否包含广告。
- App 访问权限说明；需要登录时提供审核账号。
- 隐私政策是否与当前版本代码一致。
- 测试人员、测试链接和测试反馈。
- 发布国家/地区、价格和 production 发布范围。

这些声明涉及法律和经营责任，系统可以生成建议和检查清单，但不能代替账号负责人确认事实。新注册的个人开发者账号还可能需要先满足 Google 要求的封闭测试人数和持续时间，再申请 production 权限。

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

- service account 所属 Google Cloud 项目没有启用 Android Publisher API。
- 包名没在 Play Console 预创建。
- service account 没权限。
- 隐私政策仍是占位地址或公网不可访问。
- versionCode 冲突。
- metadata 不完整。
- Play API 临时失败。

处理：

- `play_api_disabled`：在 service account 所属 Google Cloud 项目的 API 库启用 `androidpublisher.googleapis.com`，等待数分钟后重新验证。它不是 Play Console 的 App 权限问题。
- `package_not_precreated`：先去 Play Console 创建 App。
- `service_account_permission`：先补权限。
- `metadata_incomplete`：检查真实隐私政策 URL、名称、描述、图标和截图。
- `version_code_conflict`：提高 versionCode 后重试。
- `play_api_transient`：稍后重试。

## 8. 你可以直接照着做的一套最短流程

已经部署好的甲方云端直接打开：

```text
https://hcapply.npzsk.com.cn/dashboard
```

如果右上角显示“未设置访问令牌”，管理员在服务器读取 `/opt/hcapply/craftsman/secrets/API_TOKEN`，然后在“访问设置”保存。不要把令牌发到聊天、截图或文档中。

只有首次部署或本地开发才需要下面的启动命令：

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
2. 先到“发布配置”同步并验证包名，确认“Play 可访问”。
3. 回到“找机会”，选择“一键自动生成并上架”。
4. 填写关注方向并点击右上角按钮。
5. 如果停在“等待选择”，到“可做的 App”点击“选择这个需求”。
6. 在“生成进度”等待质量检查和 internal 提交。
7. 最终到 Play Console 对应 App 的 Internal testing 页面确认新版本。

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

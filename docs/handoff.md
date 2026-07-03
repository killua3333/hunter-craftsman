# Hunter-Craftsman 项目交接说明

本文是交接入口。目标是让接手方能快速知道：项目能做什么、怎么启动、怎么跑一轮、哪些地方还不能承诺给客户。

## 一句话说明

Hunter-Craftsman 是一个用于探索 Android 工具类 App 机会的 AI 流水线：先从 Google Play 找真实需求，再生成 Android MVP，最后尝试提交到 Google Play 内部测试轨道。

## 当前代码分支

当前开发分支：

```text
fix/worker-deadlock-and-play-api-proxy
```

建议交接后先基于这个分支继续验证，再决定是否合并到主分支。

## 目录结构

```text
hunter-craftsman/
  hunter/                         # Agent A：Google Play 需求发现
  craftsman/                      # Dashboard、Agent B、Agent C
    craftsman/api/app.py          # Dashboard API
    craftsman/dashboard.html      # 单文件前端工作台
    craftsman/orchestrator/       # 生成、质量、验证流程
    craftsman/publisher/          # Google Play internal track 发布
    scripts/serve_dashboard.py    # 本地启动入口
    tests/                        # Craftsman 测试
  scheduler/                      # 自动调度脚本
  docs/                           # 文档
```

## 必备配置

复制环境变量模板：

```powershell
cd D:\A\hunter-craftsman\craftsman
copy .env.example .env
```

关键配置项：

```env
DEEPSEEK_API_KEY=...
ANDROID_RELEASE_TRACK=internal
ANDROID_HOME=C:\Users\Administrator\AppData\Local\Android\Sdk
ANDROID_SDK_ROOT=C:\Users\Administrator\AppData\Local\Android\Sdk

# 真实上传时需要
GOOGLE_PLAY_SERVICE_ACCOUNT_FILE=./secrets/play-sa.json
ANDROID_KEYSTORE_PATH=./secrets/release.jks
ANDROID_KEYSTORE_PASSWORD=...
ANDROID_KEY_ALIAS=release
ANDROID_KEY_PASSWORD=...
PACKAGE_POOL=com.yourbrand.template001,com.yourbrand.template002
```

如果本机访问 Google 服务需要代理，启动服务前设置：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:10808"
$env:HTTPS_PROXY="http://127.0.0.1:10808"
```

不要把 `.env`、`secrets/`、`workspace/`、数据库和构建产物提交到 Git。

## 启动方法

```powershell
cd D:\A\hunter-craftsman\craftsman
$env:PYTHONPATH="D:\A\hunter-craftsman\hunter\src;D:\A\hunter-craftsman\craftsman"
python .\scripts\serve_dashboard.py
```

浏览器打开：

```text
http://127.0.0.1:8791/dashboard
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8791/health
```

## 真实业务流程

1. 在“找机会”页输入搜索方向或使用默认方向。
2. 点击开始发现。
3. 系统创建 discovery run，并逐步执行：搜索 Play、扫描竞品、抓取低分评论、统计痛点、生成候选、等待人工选择。
4. “可做的 App”页展示真实候选需求。候选来自 `discovery_candidates`，不是从历史 run 或 fallback demo 拼出来的。
5. 人工选择候选后才创建代码生成任务。
6. Agent B 生成 Android 项目并输出质量报告。质量不足时不应自动进入发布。
7. Agent C 做发布前检查、签名、AAB 构建，并提交 internal track 或给出需要人工处理的原因。

## 三个模块的真实状态

### Agent A：需求发现

当前已经改为真实 Google Play 采集链路。成功时会记录：

- 搜索词
- 竞品 App
- 评分、安装量、更新时间、描述
- 低分评论
- 痛点聚类
- 候选机会
- 淘汰原因
- 最终选择理由

重要原则：

- Play 搜索完全失败时，应该失败并提示原因，不能生成假候选。
- 评论不足时可以生成 `mixed` 候选，但不应自动进入 Agent B。
- 前端应展示过程和证据，让人能复核。

### Agent B：代码生成

当前目标是“广覆盖，但有质量门槛”。生成后会检查：

- 是否有主界面
- 是否有可交互控件
- 是否体现本地状态或持久化
- 是否有截图、图标、metadata
- 是否存在把“广告、崩溃、订阅”等痛点误当功能的情况
- Gradle 构建是否成功

质量分建议：

- `>= 75`：允许进入发布。
- `60-74`：可以预览，但不建议上架。
- `< 60`：应修复或缩小范围。

当前最大风险也是 Agent B：它可能生成能编译但产品感不足的 App。后续应持续把质量报告和自修复做强。

### Agent C：Google Play internal 发布

Agent C 现在的稳定目标只到 internal track。

必须明确：Google Play Developer API 不能自动创建新的 Play Console App。正确做法是：

1. 人工在 Play Console 批量预创建 App。
2. 把这些包名写入 `PACKAGE_POOL`。
3. 系统从包名池分配包名。
4. 发布前用 Play API 验证 service account 能访问该包名。
5. 成功提交 internal 后，包名永久占用。

如果出现 `package_not_precreated`，说明包名没有在 Play Console 预创建，或 service account 没有权限。

## 常见失败原因

| 现象 | 常见原因 | 处理方式 |
| --- | --- | --- |
| 机会发现失败 | 代理未生效、Google Play 请求失败、评论抓取被限制 | 检查 `HTTP_PROXY` / `HTTPS_PROXY`，重试不同搜索词 |
| 发现很快失败 | Play 搜索阶段就失败，没有进入评论抓取 | 看技术日志里的 discovery event |
| 代码生成失败 | LLM 配置缺失、Gradle 找不到 Android SDK、需求范围过大 | 检查 `DEEPSEEK_API_KEY`、`ANDROID_HOME`、质量报告 |
| App 质量低 | 主流程不清晰、生成内容模板化、痛点被误当功能 | 选择更聚焦的候选，或人工调整需求后重试 |
| 发布失败 `package_not_precreated` | 包名未在 Play Console 预创建 | 预创建包名并加入 `PACKAGE_POOL` |
| 发布失败权限不足 | service account 没有该 App 权限 | 在 Play Console 用户权限中授权 |
| 上传超时 | 网络或代理问题 | 用代理启动服务，查看 Google API 请求错误 |

## 交接验收建议

接手方至少应跑通以下检查：

```powershell
cd D:\A\hunter-craftsman
python -m py_compile craftsman\craftsman\api\app.py craftsman\craftsman\orchestrator\quality.py
cd craftsman
python -m pytest tests\test_real_discovery_api.py tests\test_quality_report.py tests\test_release_preflight.py -q
```

再通过 Dashboard 跑一轮：

1. 真实发现候选。
2. 人工选择候选进入生成。
3. 查看质量报告。
4. 真实提交到 Google Play internal track；如果配置不完整，记录 failure_class 和操作建议。
5. 如 Play Console 包名池已经准备好，再尝试真实 internal track 上传。

## 后续优先级

1. 修复并强化包名池分配，确保 B/C 永远使用 Play Console 已预创建且可访问的包名。
2. 继续提高 Agent B 生成质量，减少“像示例程序”的输出。
3. 对需求池做去重和归档，避免历史候选污染客户视图。
4. 给 Dashboard 增加更细的阶段进度和错误解释。
5. 将真实上架链路沉淀成自动化验收脚本。

## 2026-07-02 B/C 质量与包名池更新

本次更新已经完成两件事：

1. Agent B 质量升级到 MVP 合约 v2。
2. Agent C 包名池产品化到 Google Play internal track。

### Agent B 当前行为

- 生成前写 `implementation_plan.json`。
- 质量报告使用 `AppBuildQualityReport v2`。
- 质量分 `>= 75` 才允许自动进入发布。
- `60-74` 标记为“可以预览，建议打磨”。
- `< 60` 标记为需要修复。
- 最多 3 轮质量修复，第三轮缩小到一个主功能。

### Agent C 当前行为

- 包名必须来自 `PACKAGE_POOL`。
- Dashboard 提供同步、验证、释放、标记无效接口。
- 包名池耗尽时，生成阶段会直接提示先处理包名池。
- `package_not_precreated` 和 `service_account_permission` 会把包名标记为无效。
- `internal_submitted` 后包名永久占用。

### 最新验证

已通过相关回归：

```text
54 passed
py_compile passed
node --check dashboard JS passed
git diff --check passed
```

下一阶段建议优先继续做 Agent B 的真实 App 体验提升和 Agent A 的需求去重，而不是继续扩大发布范围。

## 2026-07-03 真实端到端验证

本轮已经在真实 Google Play Console 环境跑通一条完整链路：

```text
Google Play 真实需求发现 -> 候选入池 -> 自动选择 Checklist App -> Android MVP 生成 -> 质量分 100 -> 构建 AAB -> 上传 Google Play internal testing
```

验证结果：

| 项目 | 结果 |
| --- | --- |
| discovery_run_id | `disc-680205358b` |
| run_id | `4aa416a6-181e-4b10-95c4-c584f03cf485` |
| release_id | `rel-4aa416a6-181e-4b10-95c4-c584f03cf485` |
| App 方向 | checklist app |
| 生成 App | Checklist App MVP |
| 包名 | `com.AEM.template002` |
| 质量分 | `100` |
| Google Play track | `internal` |
| Play Console 状态 | 已面向内部测试人员发布 |
| versionName / versionCode | `1.0.1` / `3` |
| Play edit id | `09795040429092485850` |

需要特别说明：这次发布第一次尝试同步商店素材时失败，系统随后按稳定策略重试为“只上传 AAB 到 internal track”，最终成功。因此 Play Console 能看到内部测试版本，但不会显示生成 App 的真实截图/描述更新。App 的真实界面预览需要在 Dashboard、生成截图或安装 APK 中查看。

本次生成产物位于：

```text
craftsman/workspace/4aa416a6-181e-4b10-95c4-c584f03cf485/artifacts/
```

关键文件：

```text
app-debug.apk
app-release.aab
screenshots/screenshot_1.png
screenshots/screenshot_2.png
screenshots/screenshot_3.png
```

生成的 Checklist MVP 具备：标题输入、备注输入、添加按钮、空状态、任务列表、完成复选框、完成项删除线、本地 SharedPreferences 保存。

## 当前产品认知补充

### Play Console 能看到什么

Google Play Console 是发布后台，不是 App 预览器。它能看到：App 壳子、包名、版本、AAB、内部测试轨道、测试人员、商店素材。它不能像手机一样直接展示 App 的交互界面。

因此面向客户解释时，应说明：

- Play Console 证明“已经提交到 internal testing”。
- App 长什么样，应在 Dashboard 的生成进度/截图预览、生成截图文件或测试手机下载后查看。
- 如果商店素材同步失败但 AAB 上传成功，Console 里的名称可能仍是预创建 App 名称，例如 `AEM Template 002`，而不是生成 App 名称。

### 包名池的真实边界

一个新 App 必须占用一个新的包名。已经 `submitted_internal` 的包名视为永久占用，不应释放或复用。

当前稳定模型仍是：

1. 人在 Play Console 预创建 App 和包名。
2. 将包名写入 `.env PACKAGE_POOL`。
3. Dashboard 同步配置。
4. Dashboard 验证包名。
5. 系统自动分配可用包名并发布 internal track。

Google Play Developer API 不能稳定自动创建 Play Console App，所以包名池耗尽后仍需要人工批量创建新 App。后续可以做“包名池准备向导”，但不应承诺 API 自动创建 App。

### Dashboard 待优化点

本轮使用中暴露出几个面向客户的关键体验问题：

- 发布配置页需要持续显示完整包名池，而不是只显示汇总数字。
- 已提交 internal 的包名不应展示“释放/标记无效”等容易误操作的主按钮。
- 生成进度页应直接展示本次发布的 App 方向、核心功能、包名、版本和截图预览。
- 自动刷新会造成页面闪烁，演示时建议关闭；产品上应减少整块重绘。
- Google Play store listing 素材同步失败后，目前会降级为只上传 AAB；需要在 Dashboard 用人话明确提示“已发布测试版本，但商店素材未更新”。

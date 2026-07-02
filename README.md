# Hunter-Craftsman

Hunter-Craftsman 是一个面向 Android 工具类 App 的三段式 AI 流水线：

1. 从 Google Play 搜索真实竞品、评论和差评痛点，形成可复核的需求候选池。
2. 将选中的需求生成 Kotlin + Compose Android MVP，并做编译、交互、素材和质量检查。
3. 将达到质量门槛的 App 构建为 AAB，提交到 Google Play internal track 内部测试轨道。

当前项目仍处在产品化落地阶段，不是“全自动批量上架 production”的成熟 SaaS。交接时请重点看 [docs/handoff.md](docs/handoff.md)。

## 系统组成

| 模块 | 目录 | 当前职责 |
| --- | --- | --- |
| Hunter / 需求发现 | `hunter/` | 生成搜索词，采集 Google Play 竞品、详情和低分评论，输出候选需求与证据。 |
| Craftsman / App 生成 | `craftsman/` | 需求收敛、代码生成、Gradle 构建、质量评分、产物生成。 |
| Publisher / 内测发布 | `craftsman/craftsman/publisher/` | 发布前检查、签名、AAB 构建、Play Edits API internal track 提交。 |
| Dashboard / 工作台 | `craftsman/craftsman/dashboard.html` + `craftsman/craftsman/api/app.py` | 给用户看的机会发现、需求池、生成进度和技术日志。 |

## 当前真实能力

- 可以启动本地 Dashboard：`http://127.0.0.1:8791/dashboard`
- 可以发起真实 Google Play 需求发现；失败时不会再自动伪造 demo 需求。
- 发现结果进入需求池，默认由人选择后再进入代码生成。
- Agent B 可以生成 Android 项目、APK/AAB 产物，并输出质量报告。
- Agent C 可以执行 Google Play internal track 发布链路；真实上传要求包名已经在 Play Console 预创建并授权给 service account。

## 重要限制

- Google Play Developer API 不能自动创建一个全新的 Play Console App。必须先由人预创建包名，系统再从包名池分配使用。
- 生成 App 的质量还需要继续提升。质量分低于发布门槛的结果不应该自动进入上架流程。
- production 发布、商业模式实验、订阅/支付、云同步不属于当前稳定范围。
- `.env`、`secrets/`、`workspace/`、数据库和构建产物不能提交到 Git。

## 本地启动

推荐在 Windows PowerShell 中运行：

```powershell
cd D:\A\hunter-craftsman\craftsman
copy .env.example .env
pip install -e ".[dev,publish]"
$env:PYTHONPATH="D:\A\hunter-craftsman\hunter\src;D:\A\hunter-craftsman\craftsman"
python .\scripts\serve_dashboard.py
```

如果本机需要代理访问 Google / Google Play：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:10808"
$env:HTTPS_PROXY="http://127.0.0.1:10808"
```

打开：

```text
http://127.0.0.1:8791/dashboard
http://127.0.0.1:8791/health
```

## 一轮真实流程

1. 打开 Dashboard。
2. 在“找机会”页输入或确认搜索方向，点击开始发现。
3. 等待阶段进度完成：搜索 Play、扫描竞品、抓取评论、聚类痛点、生成候选。
4. 在“可做的 App”页查看候选需求、证据、评分和来源 App。
5. 选择一个候选进入生成。
6. 在“生成进度”页查看 Agent B 质量分、失败原因和是否允许进入发布。
7. 质量达标后准备 release，确认后提交到 internal track。

## Google Play 发布前提

真实 internal track 上传必须满足：

- `PUBLISHER_DRY_RUN=false`
- `GOOGLE_PLAY_SERVICE_ACCOUNT_FILE` 指向有效 service account JSON
- `ANDROID_KEYSTORE_PATH`、`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD` 可用
- `PACKAGE_POOL` 中的包名已经在 Play Console 预创建
- service account 对这些 App 有测试轨道发布权限
- Android SDK 或 Docker builder 可用

更完整的配置清单见 [docs/play-console-setup-checklist.md](docs/play-console-setup-checklist.md)。

## 测试

常用快速校验：

```powershell
cd D:\A\hunter-craftsman
python -m py_compile craftsman\craftsman\api\app.py craftsman\craftsman\orchestrator\quality.py
cd craftsman
python -m pytest tests\test_real_discovery_api.py tests\test_quality_report.py tests\test_release_preflight.py -q
```

完整测试可运行：

```powershell
cd D:\A\hunter-craftsman
python -m pytest -q
```

完整测试依赖本机 Python 环境、Android 构建环境、部分 Google Play 配置和网络状态。

## 文档入口

- [docs/handoff.md](docs/handoff.md)：交接总说明，建议第一份阅读。
- [docs/operations-manual.md](docs/operations-manual.md)：日常使用和排障。
- [docs/demo-script.md](docs/demo-script.md)：演示流程。
- [docs/agent-a-demand-discovery.md](docs/agent-a-demand-discovery.md)：需求发现说明。
- [docs/agent-b-code-quality.md](docs/agent-b-code-quality.md)：代码生成质量说明。
- [docs/agent-c-internal-testing.md](docs/agent-c-internal-testing.md)：Google Play internal track 发布说明。
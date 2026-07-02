# Hunter-Craftsman 日常操作手册

本文面向日常使用和维护人员，尽量不用内部术语。

## 1. 启动服务

```powershell
cd D:\A\hunter-craftsman\craftsman
$env:PYTHONPATH="D:\A\hunter-craftsman\hunter\src;D:\A\hunter-craftsman\craftsman"
python .\scripts\serve_dashboard.py
```

如需代理：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:10808"
$env:HTTPS_PROXY="http://127.0.0.1:10808"
```

打开：

```text
http://127.0.0.1:8791/dashboard
```

## 2. 页面怎么用

### 找机会

这里用于发起真实 Google Play 需求发现。

可做的操作：

- 输入或调整搜索方向。
- 选择人工确认或自动进入生成。
- 查看当前阶段：搜索、扫描竞品、抓取评论、分析痛点、生成候选。
- 查看失败原因和下一步处理建议。

### 可做的 App

这里展示真实需求候选。每个候选应包含：

- App 名称
- 细分领域
- 目标用户
- 用户抱怨最多的问题
- 竞品缺口
- 建议先做的功能
- 市场热度、开发适合度、证据强度
- 来源 App 和评论痛点摘要

默认需要人工点击“进入生成”后，系统才开始写 App。

### 生成进度

这里展示已经进入代码生成和发布的任务。

重点看：

- 是否生成成功
- App 质量分
- 是否建议发布
- 失败原因
- 是否已经准备 release
- 是否提交到 internal track

### 技术日志

这里保留 run_id、release_id、原始事件和错误详情，供开发者排查。

## 3. 跑一轮真实流程

1. 启动服务并打开 Dashboard。
2. 在“找机会”页点击开始发现。
3. 等待阶段进度完成。
4. 到“可做的 App”页选择一个候选。
5. 点击进入生成。
6. 到“生成进度”页等待构建和质量检查。
7. 质量达标后再进入发布。
8. 如果是真实上架，确认 `PUBLISHER_DRY_RUN=false` 并检查包名池。

## 4. Google Play internal track 发布

发布前必须确认：

- Play Console 已经预创建对应包名。
- `PACKAGE_POOL` 中只放已预创建、已授权的包名。
- service account 有 internal testing 发布权限。
- 签名 keystore 可用。
- Android SDK 或 Docker builder 可用。
- 隐私政策 URL、metadata、图标、截图存在。

如果只是演练链路，保持：

```env
PUBLISHER_DRY_RUN=true
```

真实上传时改为：

```env
PUBLISHER_DRY_RUN=false
```

## 5. 常见问题

### 点击开始发现后失败

先看“找机会”页的阶段进度和“技术日志”。常见原因：

- 本机代理没有设置到服务进程。
- Google Play 搜索请求失败。
- 评论抓取失败或评论数量不足。
- seed query 太窄，搜不到有效竞品。

处理：

- 用代理环境变量重启服务。
- 换更宽的搜索词，例如 checklist、timer、habit tracker、unit converter。
- 保留失败记录，不要用假数据补齐。

### 发现成功但没有进入生成

这是正常行为。默认模式是人工确认，候选会先进入“可做的 App”。只有人工点击进入生成，才会创建生成任务。

### 代码生成失败

常见原因：

- LLM key 缺失或请求失败。
- Android SDK 路径未配置。
- Gradle 构建失败。
- 生成结果没有主界面、交互控件或本地状态，被质量门槛拦截。

处理：

- 检查 `.env` 里的 `DEEPSEEK_API_KEY`。
- 设置 `ANDROID_HOME` 和 `ANDROID_SDK_ROOT`。
- 查看任务质量报告和 build log。
- 必要时选择更聚焦的候选重试。

### 发布失败：包名未创建

Google Play API 不能创建新的 App。需要人工在 Play Console 先创建 App，并把包名加入 `PACKAGE_POOL`。

### 发布失败：权限不足

在 Play Console 的 Users and permissions 中给 service account 授权。至少需要查看 App 信息、管理测试轨道、发布到测试轨道。

## 6. 日常维护建议

- 每次真实上传前检查包名池剩余量。
- 定期归档低质量或重复需求候选。
- 不要把失败任务伪装成成功候选。
- 不要把 demo、fallback、assumption 数据放进客户默认视图。
- 每次大改后至少跑 discovery、quality、release preflight 三类测试。
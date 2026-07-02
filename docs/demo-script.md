# 演示脚本

本文用于给客户、团队成员或评审演示当前系统。建议实话实说：系统已经能跑真实链路，但仍处在产品化打磨阶段。

## 演示前准备

1. 确认服务可启动。
2. 确认代理可用，尤其是 Google Play 搜索和 Google API。
3. 如果只演示流程，设置 `PUBLISHER_DRY_RUN=true`。
4. 如果演示真实 internal track 上传，确认 Play Console 已预创建包名并授权。
5. 清楚说明：Google Play API 不能自动创建全新 App，包名池需要提前准备。

## 启动

```powershell
cd D:\A\hunter-craftsman\craftsman
$env:PYTHONPATH="D:\A\hunter-craftsman\hunter\src;D:\A\hunter-craftsman\craftsman"
$env:HTTP_PROXY="http://127.0.0.1:10808"
$env:HTTPS_PROXY="http://127.0.0.1:10808"
python .\scripts\serve_dashboard.py
```

打开：

```text
http://127.0.0.1:8791/dashboard
```

## 推荐讲法

可以这样介绍：

> 这个系统不是让大模型凭空猜需求，而是先去 Google Play 搜索真实竞品和低分评论，形成一个可复核的需求池。人可以看到证据、评分和淘汰原因，再决定是否让系统生成 App。生成后还会做质量检查，达标才允许进入 Google Play 内部测试发布链路。

## 演示步骤

### 1. 找机会

进入“找机会”页。

讲解重点：

- 这里可以输入或调整搜索方向。
- 系统会分阶段执行真实采集。
- 如果 Google Play 请求失败，页面会显示失败原因，而不是塞一个假需求。

操作：

1. 输入方向，例如 `simple checklist, timer, habit tracker`。
2. 点击开始发现。
3. 等待阶段进度变化。

### 2. 看需求池

进入“可做的 App”页。

讲解重点：

- 候选需求来自真实搜索结果和评论证据。
- 每个候选都有市场热度、开发适合度、证据强度。
- 默认由人选择，不会直接自动写代码。

操作：

1. 展开候选。
2. 查看来源 App、痛点摘要和建议功能。
3. 选择一个候选进入生成。

### 3. 看生成进度

进入“生成进度”页。

讲解重点：

- 系统会生成 Android 项目。
- 编译、截图、图标、metadata 和 UI 质量都会进入质量报告。
- 质量不够时会阻断发布。

操作：

1. 等待任务完成。
2. 查看质量分和失败原因。
3. 如果达标，准备发布。

### 4. 发布到 internal track

如果是 dry-run：

- 说明这是发布链路演练，不会真的上传 Google Play。

如果是真实上传：

- 说明包名必须来自 Play Console 预创建包名池。
- 展示 internal track 提交状态。

## 不建议演示的说法

不要说：

- “系统可以完全自动创建 Google Play App。”
- “任何需求都能生成可上架产品。”
- “已经可以自动推 production。”

建议说：

- “当前稳定目标是 internal track。”
- “包名和权限需要一次性预配置。”
- “生成质量是当前最重要的持续优化方向。”
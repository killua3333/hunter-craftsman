# 前端工作台规格

## 信息架构

Dashboard 使用单页 HTML，不引入前端构建系统。顶部四个视图：机会发现、需求池、任务进度、高级日志。

## 机会发现

展示 Agent A/B/C 状态、internal track 模式、环境检查和最新机会判断。用户可以点击“启动机会发现”触发 `/dashboard/api/autopilot`。

## 需求池

数据来自 `/dashboard/api/overview.opportunities`。每张卡片展示 App 名、细分领域、目标用户、痛点、竞品缺口、推荐功能、评分、数据质量和证据。

## 任务进度

数据来自 `/dashboard/api/overview.pipeline`。每条流水线固定展示 A 发现需求、B 生成 App、C 内部测试上架三段状态。

## 高级日志

保留 runs、releases、audit、events，用于调试和重试。普通用户默认不用理解 run_id/release_id。

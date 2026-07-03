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

## 发布配置页

面向客户展示 Google Play 发布准备情况，避免让用户去技术日志里找原因。

必须展示：

- 可用包名数量。
- 已占用包名数量。
- 无效包名数量。
- 包名列表、状态、错误原因。
- “同步配置”“验证包名”“释放”“标记无效”操作。

推荐文案：

- “请先在 Play Console 批量创建 App，系统会自动检查并使用这些包名。”
- “可用包名不足，请先同步或验证包名池。”
- “这个包名无法访问，请检查 Play Console 是否已创建并授权。”

不要在普通用户区域显示过多内部术语。`run_id`、`release_id`、原始异常堆栈只放在“技术日志”。

## 生成质量展示

“生成进度”页应展示：

- 质量分。
- 建议发布 / 可以预览，建议打磨 / 需要修复。
- 主要扣分原因。
- 下一步建议。

普通用户文案不要直接暴露 `quality_gate_blocked`、`failure_classes` 等内部字段；这些字段可以放到技术日志。

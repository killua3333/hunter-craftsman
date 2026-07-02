# Agent A 需求发现规则

Agent A 负责发现适合快速生成 Android MVP 的工具类机会。

## 输出字段

除原有 requirement 外，必须尽量输出：`niche`、`target_users`、`pain_points`、`competitor_gap`、`opportunity_score`、`build_fit_score`、`decision_reason`、`rejected_candidates`。

## 筛选规则

优先纯前端、本地存储、无需账号、无需支付、无需服务器的工具类 App。默认最多 3 个核心功能。`build_fit_score` 低于 60 且存在替代候选时，自动跳过当前方向。

## 数据质量

真实 Play 数据使用 `measured`；混合来源使用 `mixed`；没有真实数据时使用 `assumption`，且 opportunity_score 不得高于 65。

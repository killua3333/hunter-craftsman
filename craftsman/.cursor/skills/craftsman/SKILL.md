---
name: craftsman
description: Agent B iOS 工匠车间。处理 Agent A 的 requirement JSON、Gate 分析、SwiftUI 生成、xcodebuild Reflexion、Fastlane 发版。同机无人值守时用 HTTP API + callbacks 目录。
---

# Craftsman (Agent B)

## 何时使用

- 收到 `opportunity_id` + `requirement.v1.json` 需求
- 需要向 Agent A 返回 `craftsman-feedback.v1.json`
- iOS SwiftUI 实现、编译修复、截图/Icon、TestFlight

## 工作流

1. `POST /v1/opportunities/{id}/analyze` — 未通过则改需求，不要 implement
2. `POST /v1/opportunities/{id}/implement` — 取 `run_id`，轮询 `GET /v1/runs/{run_id}`
3. 读 `callbacks/{opportunity_id}_*.json` 或 Webhook

## 关键路径

- 编排：`craftsman/orchestrator/pipeline.py`
- Gate：`craftsman/gate.py`
- 模板：`templates/ios-app/`
- Schema：`schemas/`

## Mac 要求

xcodebuild / Fastlane 仅在 Darwin 可用；Windows 开发设置 `SKIP_XCODEBUILD=true`。

## Windows 交互 Demo

每次 `implement` 完成后，工作区根目录必有 **`index.html`**（双击浏览器预览）。`artifacts/demo.html` 为跳转入口；反馈字段 `artifacts.preview_html`。

- 模板：`templates/web-demo/`（timer / calculator / list）
- 逻辑：`craftsman/tools/web_demo.py` → `ensure_windows_demo()`

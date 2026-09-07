# Craftsman（Agent B）— 分阶段 App 生产与发布车间

接收 Agent A 的结构化需求，按固定产品阶段生成 Android/iOS 工程，执行编译与质量修复，生成预览和 Agent C 发布交接材料。当前主目标为 Android。

Agent B v3 将一次生成拆分为：产品定义、体验设计、核心功能、功能完善、体验完善、检测修复和发布候选。每个阶段均持久化，失败后可在同一工作区重试并保留检查记录。

## 同机无人值守架构

- **HTTP API**（`127.0.0.1:8791`）+ **SQLite 任务队列** + **后台 Worker 线程**
- Agent A 通过 HTTP 调用；反馈 JSON 写入 `callbacks/`（可选 Webhook）
- 生产环境请在 **macOS + Xcode + XcodeGen** 上运行

## 快速开始

```powershell
cd e:\agent\craftsman
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
copy .env.example .env
python -m craftsman.cli serve
```

另开终端：

```powershell
python examples\agent_a_client.py
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/opportunities/{id}/analyze` | 同步 Gate，返回 feedback JSON |
| POST | `/v1/opportunities/{id}/implement` | 异步实现，返回 `run_id` |
| GET | `/v1/runs/{run_id}` | 查询状态与 feedback |
| GET | `/v1/runs/{run_id}/events` | 查询阶段事件（支持 after_id/limit） |
| POST | `/v1/runs/{run_id}/cancel` | 取消 |
| POST | `/v1/releases/validate-handoff` | 校验 release_handoff schema |
| POST | `/v1/releases/prepare` | 预备发布并执行 policy check |
| POST | `/v1/releases/{release_id}/approve` | 人工审批（approved/rejected） |
| POST | `/v1/releases/{release_id}/submit` | 提交发布（受 policy/approval 闸门约束） |
| GET | `/v1/releases/{release_id}` | 查看 release 独立状态 |
| GET | `/v1/audit/replay` | 审计日志回放（按 run/release） |

### Feedback 格式（→ Agent A）

见 `schemas/craftsman-feedback.v1.json`。

## Mac 前置依赖

```bash
xcode-select --install
brew install xcodegen fastlane
```

在 `.env` 中设置 `SKIP_XCODEBUILD=false`、`SKIP_FASTLANE=false`。

## 配置

见 `.env.example`：

| 变量 | 用途 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `DEEPSEEK_CHAT_MODEL` | 反馈 Agent A（Gate 语义评审），默认 `deepseek-chat` |
| `DEEPSEEK_PRO_MODEL` | 写 Swift 源码 + Reflexion 修错，默认 `deepseek-v4-pro` |
| `CODING_PROVIDER` | 推荐 `deepseek_harness`（DeepSeek 官方 Harness SDK）；`deepseek_json` 为旧兼容模式 |
| `DEEPSEEK_HARNESS_MODEL` | 官方 Harness 使用的模型，默认 `deepseek-v4-pro` |
| `DEEPSEEK_HARNESS_REASONING_EFFORT` | 推理强度：`off`、`low`、`high` 或 `max` |
| `DEEPSEEK_HARNESS_MAX_TOKENS` | 每个编码阶段的最大输出 token 数 |
| `CODEX_DEEPSEEK_MODEL` | Codex Harness 使用的 DeepSeek 模型，默认 `deepseek-v4-pro` |
| `CODEX_DEEPSEEK_REASONING_EFFORT` | 推理强度：`low`、`high` 或 `max` |
| `CODING_AGENT_COMMAND_JSON` | 工作区执行器的非交互命令参数 JSON 数组 |
| `CODING_AGENT_ALLOWED_EXECUTABLES` | 允许启动的编码 CLI 白名单 |
| `CODING_AGENT_TIMEOUT_SECONDS` | 单次编码阶段的最长执行时间 |
| `CALLBACK_DIR` | 反馈 JSON 目录 |
| `SKIP_XCODEBUILD` | Windows 上设为 `true` 走 Demo 产物模式 |
| `API_TOKEN` | API 轻鉴权 token（可走 secret store） |
| `SECRET_PROVIDER`/`SECRET_STORE_DIR` | secret 读取策略（env/file/fallback） |
| `WEBHOOK_MANDATORY` | 强制签名 webhook 模式 |
| `RELEASE_REQUIRE_HUMAN_APPROVAL` | submit 前是否要求人工审批 |
| `RELEASE_REQUIRE_POLICY_CHECKS` | submit 前是否要求 policy 通过 |
| `AUDIT_RETENTION_DAYS` | 审计日志保留天数 |
| `NATIVE_BACKEND_POOL` | native backend 目标池（逗号分隔） |

## Windows Demo 模式

当主机不是 macOS（或 `SKIP_XCODEBUILD=true`）时，Craftsman 会自动切换到 Demo 产物模式：

- 使用 **deepseek-v4-pro** 生成 `Sources/*.swift`（无 Key 时回退 Jinja 模板）
- Gate 反馈 Agent A 的语义评审使用 **deepseek-chat**
- 生成 `artifacts/AppIcon.png`、`artifacts/screenshots/*.png`
- **每次实现**自动生成 `workspace/{run_id}/index.html`（Windows 双击即可交互预览）
- `artifacts/demo.html` 会跳转到上级 `index.html`；反馈 `artifacts.preview_html` 指向交互 Demo
- 按需求类型选择模板：番茄钟/计时器、计算器、通用列表
- 若 LLM 已输出合格 `index.html` 则优先使用，否则由内置模板渲染
- 反馈终态为 `implementation_complete`，并在 `reasons` 里说明后续发布由独立流程负责

## 测试

```powershell
pytest
```

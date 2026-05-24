# Hunter + Craftsman 操作指南（最新版）

## 1) 环境准备

### Craftsman（Agent B）

```powershell
cd craftsman
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
copy .env.example .env
```

最低建议配置：

- `DEEPSEEK_API_KEY=...`
- `API_TOKEN=...`（可选但推荐）
- Windows 开发机默认保持：
  - `SKIP_XCODEBUILD=true`
  - `SKIP_FASTLANE=true`

启动：

```powershell
python -m craftsman.cli serve
```

### Hunter（Agent A）

```powershell
cd hunter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

最低建议配置：

- `DEEPSEEK_API_KEY=...`
- `TAVILY_API_KEY=...`
- `CRAFTSMAN_API_TOKEN=...`（与 Craftsman 的 `API_TOKEN` 一致）
- `CRAFTSMAN_CONTRACT_VERSION=1.0`

---

## 2) Autopilot 全自动（推荐）

无需具体 app 描述，系统自动搜索 Play 机会 → Soft Gate → 实现 → 可选发布：

```powershell
# Terminal 1 — Craftsman
cd craftsman
python -m craftsman.cli serve

# Terminal 2 — Hunter Autopilot
cd hunter
hunter autopilot

# 含 Agent C dry-run 发布
hunter autopilot --publish
```

环境要求：

- Hunter：`DEEPSEEK_API_KEY`、`TAVILY_API_KEY`
- Craftsman 默认 Soft Gate：`GATE_MODE=soft`、`GATE_AUTO_ACCEPT=true`
- Windows 默认 `SKIP_GRADLE_BUILD=true`（demo 模式）；有 Android SDK 时可设 `false` 启用 verified 编译
- 真 live 上架见 [play-console-setup-checklist.md](play-console-setup-checklist.md)

**超时预算（秒）**：

| 命令 / 阶段 | 默认 | 说明 |
|-------------|------|------|
| `hunter run` | 600 | `--timeout` 覆盖 |
| `hunter run --autopilot` | ≥1800 | 取 `max(--timeout, 1800)`，含多轮澄清 + Docker 冷构建 |
| `hunter autopilot` | 600 | 建议 `--timeout 1800` 或更高 |
| Agent C submit ACK | 60 | 仅等待入队；终态轮询最长 1800 |
| Craftsman analyze | 90 | `CRAFTSMAN_ANALYZE_TIMEOUT_SECONDS` |

反馈字段 `verification`：

- `demo` — 跳过 Gradle 或仅 web demo 验证
- `verified` — 原生编译通过

---

## 3) 最快跑通（手动描述需求）

在 Agent B 已启动情况下，执行：

```powershell
cd hunter
.\.venv\Scripts\hunter.exe run "做一个离线番茄钟，目标是学生专注计时"
```

你会看到：

- A 侧机会分析
- B 侧异步实现进度（phase）
- 终态反馈 `implementation_complete`（或失败原因）

---

## 3) 发布治理流（prepare -> approve -> submit）

### A. 先拿到 release_handoff

可从 `sync-implement` 或异步 run 终态反馈中获得 `release_handoff`。

### B. 校验 handoff

`POST /v1/releases/validate-handoff`

- 不通过：返回 `invalid_release_handoff`
- 通过：`accepted=true`

### C. prepare（触发 policy check）

`POST /v1/releases/prepare`

- 返回：
  - `policy.passed`
  - `policy.issues`
  - `approval_required`

### D. approve（人工审批）

`POST /v1/releases/{release_id}/approve`

- `decision=approved|rejected`
- 记录审批人和备注

### E. submit（受双闸门约束，异步入队）

`POST /v1/releases/{release_id}/submit`

- 若未通过 policy：`release_policy_check_failed`
- 若未人工审批：`release_requires_human_approval`
- 双闸门都通过后立即返回 `status=submitting`（`agent_c_status=building`）；Gradle + Play 在后台 worker 执行
- 轮询 `GET /v1/releases/{release_id}` 直至 `dry_run_complete` / `published` / `failed`（建议最长 1800s）

### F. status（独立 release 生命周期）

`GET /v1/releases/{release_id}`

- 查看 `state` / `policy` / `approval`

---

## 4) 审计与回放

`GET /v1/audit/replay`

常用参数：

- `run_id`
- `release_id`
- `after_id`
- `limit`

用途：

- 回放一次 run/release 的关键事件
- 辅助事故排查与合规审计

---

## 5) Secrets 推荐用法

推荐：

- `SECRET_PROVIDER=env_file_fallback`
- `SECRET_STORE_DIR=./secrets`

可在 `secrets/` 下放：

- `API_TOKEN`
- `WEBHOOK_SECRET`
- `DEEPSEEK_API_KEY`

避免把敏感值长期放在 `.env`。

---

## 6) 产物与观测

终态反馈中重点看：

- `artifacts.metrics.phase_durations_seconds`
- `artifacts.metrics.llm_usage`
- `artifacts.metrics.alerts`
- `release_handoff.build_provenance.backend_target`

产物路径默认是 URI（`object://...`），本机调试可看 `artifacts.local_paths`。

---

## 7) 真上架（internal track）

完整配置清单见 [`play-console-setup-checklist.md`](play-console-setup-checklist.md)。

### 快速步骤

1. 配置 `play-sa.json`、`release.jks`、`ANDROID_KEY_*`
2. 安装依赖：`pip install -e ".[publish]"`（Craftsman 目录）
3. 设置 `PUBLISHER_DRY_RUN=false`、`ANDROID_RELEASE_TRACK=internal`
4. Play Console 手动创建 app（包名与 Agent A 输出一致）
5. 完成数据安全、内容分级、隐私政策 URL
6. 添加 internal 测试员 Gmail

### 一条命令发布

```powershell
# Craftsman 已启动
cd hunter
hunter run "做一个离线番茄钟" --publish
```

成功时 Agent C 返回 `agent_c_status=submitted`，Play Console → Internal testing 可见新 versionCode。

### Agent C 自动完成

- versionCode 递增（对比 Play track 与本地 Gradle）
- Gradle `bundleRelease` + release 签名
- 商店文案 / 图标 / 截图上传（来自 B 产物）
- Play Edits API：bundle → internal track → commit

### 发布 API 状态

`POST /v1/releases/{id}/submit` 在 live 模式下返回：

- `status=published`（或 `dry_run_complete` 在 dry-run 时）
- `agent_c_status=submitted`
- `upload.store_response` 含 versionCode 与 commit 信息

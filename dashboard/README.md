# Agent Pipeline Dashboard

轻量运维界面：展示 **Hunter** 搜寻过程、**Craftsman** 成品预览、**Publisher (Agent C)** 发布状态。

## 架构

- `gateway/` — FastAPI（默认 `127.0.0.1:8800`），代理 Craftsman API、提供产物静态访问、读取 `pipeline_runs/`
- `ui/` — Vite + React（开发 `5173`，构建产物输出到 `gateway/static/`）
- `../pipeline_runs/` — Hunter 写入的 `meta.json` + `hunter.jsonl`（已 gitignore）

## 快速开始

### 1. Craftsman（已有）

```powershell
cd e:\agent\craftsman
python -m craftsman.cli serve
```

### 2. Gateway

```powershell
cd e:\agent\dashboard\gateway
pip install -r requirements.txt
python main.py
```

环境变量（可选，默认读取 `craftsman/.env` 的 `API_TOKEN`）：

- `CRAFTSMAN_BASE_URL` — 默认 `http://127.0.0.1:8791`
- `PIPELINE_RUNS_DIR` — 默认 `e:\agent\pipeline_runs`

### 3. 前端

```powershell
cd e:\agent\dashboard\ui
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173

### 4. 跑流水线

```powershell
cd e:\agent\hunter
hunter run "做一个离线番茄钟" --publish
# 或
hunter autopilot --publish
```

终端会打印 `Dashboard: http://127.0.0.1:8800/pipeline/pl-...`，也可在首页「最近流水线」进入。

也可手动输入 **run_id**（与可选 **release_id**）打开历史 run。

## 生产构建（单端口）

```powershell
cd e:\agent\dashboard\ui
npm run build
cd ..\gateway
python main.py
```

访问 http://127.0.0.1:8800（静态 UI + `/api/*`）。

## 关闭 Hunter 追踪

```powershell
$env:HUNTER_PIPELINE_TRACK = "0"
```

## API 摘要

| 方法 | 路径 |
|------|------|
| GET | `/api/pipelines` |
| GET | `/api/pipelines/{id}` |
| GET | `/api/pipelines/{id}/stream` (SSE) |
| POST | `/api/pipelines/link-run` |
| GET | `/api/craftsman/runs/{id}` |
| GET | `/api/craftsman/runs/{id}/events` |
| GET | `/api/craftsman/releases/{id}` |
| GET | `/api/artifacts/runs/{id}/preview.html` |

# Hunter + Craftsman（Agent A / Agent B）

同机双 Agent 流水线：机会筛选 → Gate → 实现 → Demo 产物。

| 目录 | 角色 |
|------|------|
| [hunter/](hunter/) | Agent A：LangChain + LangGraph，输出 `AppOpportunityBlueprint` |
| [craftsman/](craftsman/) | Agent B：FastAPI 流水线，SwiftUI 生成 + Windows Demo |

## 快速开始

### 1. Craftsman（Agent B）

```powershell
cd craftsman
copy .env.example .env
# 填写 DEEPSEEK_API_KEY
pip install -r requirements.txt
pip install -e .
python -m craftsman.cli serve
```

### 2. Hunter（Agent A）

```powershell
cd hunter
copy .env.example .env
# 填写 DEEPSEEK_API_KEY、TAVILY_API_KEY
pip install -e ".[dev]"
python -m hunter.main run "做一个极简番茄钟"
```

## 编排命令

- `hunter run "…"` — A → Gate → 澄清 → B implement
- `hunter chat` — 多轮对话，满意后 `/make` 提交 B
- `hunter connect-demo "…"` — 同上（别名）

## 配置说明

- Agent A 默认模型：`deepseek-chat`
- Agent B：反馈 Gate 用 `deepseek-chat`，写码用 `deepseek-v4-pro`
- Windows 开发：`SKIP_XCODEBUILD=true`，产出 `artifacts/demo.html` 与截图

## 许可证

私有项目；上传前请勿将 `.env` 提交到 Git。

# Hunter

基于 LangChain + LangGraph 的专精 Agent 脚手架，对应「配置模型 → 系统提示词 → 工具 → ReAct 循环」的分层结构。

## Agent A 输出契约（→ Agent B）

结构化模型 `AppOpportunityBlueprint`（`src/hunter/schemas/opportunity.py`），JSON Schema 见 `schemas/agent_a_output.schema.json`。

| 字段 | 说明 |
|------|------|
| `accepted` | 是否通过极简 ROI 护栏 |
| `rejection_reason` | 未通过时的原因 |
| `app_name` | 应用名（通过时必填） |
| `core_logic` | 一句话摘要 |
| `ui_layout` | 一句话摘要 |
| `keywords` | 上架关键词 |
| `data_quality` | `measured` / `assumption` / `mixed` |
| `evidence` | `[{query, source, snippet}]` |
| `requirement` | 完整 `requirement.v1` 结构（Gate 必填字段） |

通过护栏时 `blueprint_for_agent_b(blueprint)` 返回 `requirement` 对象。

## 方案 B：双文件 Prompt + 每周学习

| 文件 | 维护方式 |
|------|----------|
| `prompts/specialist_system.md` | 人工 + 审核后小改；核心护栏 |
| `prompts/specialist_learnings.md` | **每周** `hunter learn` 根据反馈自动更新 |

`load_system_prompt()` 运行时将两者拼接后交给 Agent A。

### Agent B 反馈

反馈**原样**保存 Craftsman 输出的 JSON（`craftsman-feedback.v1.json` 格式）到 `feedback/`。

```powershell
# 从 craftsman/callbacks 同步终态反馈
.\.venv\Scripts\hunter.exe feedback sync

# 或手动保存单条
.\.venv\Scripts\hunter.exe feedback save ..\craftsman\callbacks\calc-001_r1_ready_for_release.json
```

### 每周闭环（同步 + 学习）

```powershell
# 推荐：先同步 callbacks，再归纳进 specialist_learnings.md
.\.venv\Scripts\hunter-weekly.exe

# 或分步
.\.venv\Scripts\hunter.exe learn --sync-callbacks
```

Windows 任务计划程序可每周日执行：`E:\agent\hunter\.venv\Scripts\hunter-weekly.exe`

也可：`python scripts/weekly_pipeline.py` 或 `hunter learn --sync-callbacks`。

产出：

- `prompts/specialist_learnings.md`（自动更新）
- `reports/learning-YYYY-Www.md`（周报）
- `reports/system_suggested-YYYY-Www.md`（**仅建议**，不自动改 `specialist_system.md`）

Windows 任务计划程序可每周日执行：`E:\agent\hunter\.venv\Scripts\hunter-learn.exe`

## 目录结构

```
hunter/
├── config/settings.yaml      # 模型与 agent 默认参数
├── prompts/                  # specialist_system + specialist_learnings
├── feedback/                 # Agent B 反馈（待处理 *.json）
├── reports/                  # 每周学习报告与 system 升格建议
├── schemas/                  # JSON Schema 文档
├── src/hunter/
│   ├── config.py             # 读取配置并创建 ChatModel
│   ├── prompts.py            # 加载 prompts/*.md
│   ├── messages.py           # System / Human / AI / Tool 辅助
│   ├── tools/                # @tool 定义（可接 community 现成工具）
│   ├── agents/specialist.py  # 专精 ReAct Agent
│   └── main.py               # CLI
└── tests/
```

## Message 角色

| 类型 | 作用 |
|------|------|
| `SystemMessage` | 角色与规则，每轮请求进入上下文 |
| `HumanMessage` | 用户输入 |
| `AIMessage` | 模型回复，可含 `tool_calls` |
| `ToolMessage` | 工具执行结果，对应 `tool_call_id` |

## 快速开始

```powershell
cd e:\agent\hunter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
# 编辑 .env：DEEPSEEK_API_KEY + TAVILY_API_KEY
```

```powershell
# 不调用 API，只看 Message 结构（必须带 demo 子命令）
.\.venv\Scripts\hunter.exe demo

# 多轮对话（默认）；首条可写在命令行，之后继续输入，exit 或 退出 结束
.\.venv\Scripts\hunter.exe chat
.\.venv\Scripts\hunter.exe chat "品类：无广告计算器，请 web_search 后输出机会 JSON" -v

# chat：Agent A 输出会自动规范化（features/store.keywords 等）；成功时提示「✓ 机会单已就绪」
# 满意后输入 /make → 用当前会话最后一版 accepted 机会单调用 Agent B（需 craftsman serve）
# 另开终端: cd ..\craftsman && python -m craftsman.cli serve
.\.venv\Scripts\hunter.exe chat "品类：离线番茄钟…" -v
# …对话得到 accepted JSON 后…
# /make

# 只问一句就退出
.\.venv\Scripts\hunter.exe chat "你好" --once

# 完整编排：A → Gate analyze → 澄清（最多 3 轮）→ implement
# 需要先在另一个终端运行：python -m craftsman.cli serve
.\.venv\Scripts\hunter.exe run "做一个离线番茄钟，目标是学生专注计时"
.\.venv\Scripts\hunter.exe connect-demo "做一个离线番茄钟"  # 同上
```

若已执行 `Activate.ps1`，也可直接写 `hunter demo`。

### `hunter demo` 没反应？

1. **未激活虚拟环境**：系统找不到 `hunter`，请用完整路径 `.\.venv\Scripts\hunter.exe demo`，或先执行 `.\.venv\Scripts\Activate.ps1`。
2. **漏写子命令**：只输入 `hunter` 会提示用法；必须写 `hunter demo`。
3. **中文乱码**：PowerShell 先执行 `chcp 65001`，或 ` $OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8`。

## 扩展

1. **换模型**：默认 `deepseek-chat`；**不要**用 `deepseek-reasoner`、`deepseek-v4-pro`（与工具/多轮不兼容，会报 `reasoning_content` 错误）
2. **换回 OpenAI**：`settings.yaml` 设 `provider: openai`、`name: gpt-4o-mini`，`.env` 填 `OPENAI_API_KEY`
3. **换角色**：编辑 `prompts/specialist_system.md` 或新建 prompt 并改 `agent.system_prompt`
4. **Tavily**：`.env` 配置 `TAVILY_API_KEY`，默认工具 `web_search`（`tools/tavily_search.py`）

### Tavily 配置

1. https://tavily.com 获取 `tvly-...` Key  
2. `.env`：`TAVILY_API_KEY=tvly-...`  
3. `pip install -e .`  
4. `hunter chat "用 web_search 查品类痛点后输出机会 JSON" -v`

## 依赖

- [LangChain](https://python.langchain.com/) — 模型、Message、Tool 抽象
- [LangGraph](https://langchain-ai.github.io/langgraph/) — `create_react_agent` ReAct 编排

# Hunter + Craftsman（Agent A / B / C）

同机 **三智能体** 流水线：**自动发现 Play 机会 → Gate → Android 实现 → 可选 Play internal 发布**。

| 智能体 | 目录 / 代码 | 职责 |
|--------|-------------|------|
| **Agent A（Hunter）** | [hunter/](hunter/) | Play 机会发现（Google Play 真实搜刮 + 差评分析）、requirement 编排、CLI |
| **Agent B（Craftsman）** | [craftsman/](craftsman/) · `orchestrator/` | Soft Gate、代码生成（Compose）、编译验证、产物与 handoff |
| **Agent C（Publisher）** | [craftsman/](craftsman/) · [`publisher/`](craftsman/craftsman/publisher/) | Gradle 打包、签名、隐私页、Play internal 提交 |

> B 与 C 共用同一个 `craftsman serve` 服务与 API；A 为独立 CLI，通过 HTTP 编排 B → C。

| 其他 | 说明 |
|------|------|
| [docs/](docs/) | 文档（**审查入口** → [docs/project-summary.md](docs/project-summary.md)） |
| [docker/](docker/) | Android CI 构建镜像（Agent B 验证 / Agent C 打包） |

## 最快上手

```powershell
# 1. Craftsman
cd craftsman
copy .env.example .env   # 填 DEEPSEEK_API_KEY
pip install -r requirements.txt && pip install -e .
python -m craftsman.cli serve

# 2. Hunter（另开终端）
cd hunter
copy .env.example .env   # 填 DEEPSEEK + TAVILY
pip install -e ".[dev]"
hunter autopilot --publish
```

## 常用命令

| 命令 | 说明 |
|------|------|
| `hunter autopilot` | 无需求输入，自动发现机会 → B |
| `hunter autopilot --publish` | 上述 + Agent C（默认 dry-run） |
| `hunter run "…"` | 手动描述需求 |
| `hunter chat` | 多轮对话，`/make` 提交 B |

## 自动调度（Windows）

系统含三个调度脚本，实现无人值守循环运行：

```powershell
# 手动触发一轮（推荐先试）
cd scheduler
python autopilot_loop.py --once

# 持续循环（每 30 分钟一个 app）
python autopilot_loop.py --interval 30

# 注册开机自启（管理员 PowerShell）
.\install_task.ps1 -IntervalMinutes 60
```

详见 [docs/windows-scheduler-guide.md](docs/windows-scheduler-guide.md)。

## 文档

| 读者 | 文档 |
|------|------|
| **甲方 / 业务** | [甲方项目说明（非技术版）](docs/client-overview.md) |
| **技术审查** | [项目总结](docs/project-summary.md) |
| **运维实施** | [操作指南](docs/operator-step-by-step-guide.md) · [Play 上架清单](docs/play-console-setup-checklist.md) · [Agent C 架构](docs/agent-c-architecture.md) · [Windows 调度器](docs/windows-scheduler-guide.md) |
| **前端控制台** | [前端傻瓜操作说明](docs/frontend-foolproof-guide.md) |
| **商业模式** | [AI 赚钱赎身 可行性分析](docs/business-model-ai-remission-analysis.md) |

完整索引见 [docs/README.md](docs/README.md)。

## 测试

```powershell
# 仓库根目录（推荐 CI 使用）
python -m pytest -q                              # 147 passed, 1 skipped

# 分包运行
cd craftsman && python -m pytest tests/ -q   # 99 passed, 1 skipped
cd hunter    && python -m pytest tests/ -q   # 48 passed
```

## 许可证

私有项目；勿将 `.env`、`secrets/`、`workspace/` 提交到 Git。

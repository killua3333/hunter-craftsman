# Hunter + Craftsman（Agent A / B / C）

同机三 Agent 流水线：**自动发现 Play 机会 → Gate → Android 实现 → 可选 Play internal 发布**。

| 目录 | 角色 |
|------|------|
| [hunter/](hunter/) | **Agent A**：LangGraph 发现 + 编排 CLI |
| [craftsman/](craftsman/) | **Agent B**：Gate / 实现 / 产物；**Agent C**：Gradle 打包 + Play API |
| [docs/](docs/) | 文档（**审查入口** → [docs/project-summary.md](docs/project-summary.md)） |
| [docker/](docker/) | Android CI 构建镜像 |

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

## 文档

| 读者 | 文档 |
|------|------|
| **甲方 / 业务** | [甲方项目说明（非技术版）](docs/client-overview.md) |
| **技术审查** | [项目总结](docs/project-summary.md) |
| **运维实施** | [操作指南](docs/operator-step-by-step-guide.md) · [Play 上架清单](docs/play-console-setup-checklist.md) · [Agent C 架构](docs/agent-c-architecture.md) |

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

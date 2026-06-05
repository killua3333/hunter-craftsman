# Windows 自动调度指南

## 概述

`hunter-craftsman/scheduler/` 提供了三个脚本，实现在 Windows 上无人值守循环触发完整流水线：

```
Agent A 发现(Play Store) → Agent B 生成(Android Compose) → Agent C 发布(Google Play internal)
```

底层调用等效于 `hunter autopilot --publish`，在启动前自动管理 Craftsman 服务。

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `autopilot_loop.py` | 核心循环脚本。管理 Craftsman 生命周期 + 触发 Hunter autopilot |
| `run_autopilot.bat` | 一键启动批处理。自动加载 `.env` 环境变量，透传命令行参数 |
| `install_task.ps1` | Windows Task Scheduler 注册脚本。可选系统级开机自启 |

日志输出到项目根目录 `logs/autopilot_scheduler.log`。

---

## 用法

### 方式一：手动触发一轮（推荐先验证）

```powershell
cd d:\A\hunter-craftsman\scheduler
python autopilot_loop.py --once
```

成功时你会看到：
1. Craftsman 健康检查通过
2. Hunter 调用 Play scraper 搜索并分析竞品
3. 输出 Blueprint + 编译 + 发布结果

### 方式二：持续循环运行

```powershell
python autopilot_loop.py --interval 30
```

每 30 分钟自动发一版新 app。`Ctrl+C` 退出时自动清理 Craftsman 子进程。

选项：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--interval N` | 30 | 每轮间隔（分钟） |
| `--once` | false | 只跑一轮后退出 |
| `--no-publish` | false | 跳过 Agent C 发布（只发现+生成） |
| `--max-rounds N` | 0 | 最大轮数（0=无限） |

### 方式三：一键启动批处理

```powershell
cd d:\A\hunter-craftsman\scheduler
run_autopilot.bat --once
run_autopilot.bat --interval 60
```

批处理自动加载 `hunter/.env` 和 `craftsman/.env`。

### 方式四：系统级开机自启（管理员 PowerShell）

```powershell
# 安装（每小时触发一轮）
cd d:\A\hunter-craftsman\scheduler
.\install_task.ps1 -IntervalMinutes 60

# 手动触发一次测试
schtasks /run /tn HunterCraftsman_AutoPilot

# 卸载
.\install_task.ps1 -Uninstall
```

---

## 调度器工作流程

```
第 N 轮开始
  ├─ 检查 Craftsman 是否 healthy (GET /health)
  ├─ 若未运行：自动启动 python -m craftsman.cli serve 子进程
  ├─ 轮询 /health 等待就绪（最多 60 秒）
  ├─ 触发 python -m hunter.main autopilot --publish
  │   ├─ Agent A: Play Store 竞品扫描 + 差评分析
  │   ├─ Agent B: 代码生成 + 编译验证
  │   └─ Agent C: Gradle 打包 + 签名 + Play internal 上传
  ├─ 记录本轮结果
  └─ 休眠 N 分钟 → 下一轮
```

---

## 日志与监控

调度器日志写入 `d:\A\hunter-craftsman\logs/autopilot_scheduler.log`，同时在控制台实时输出。

轮次结果由 `run_autopilot.bat` 控制台打印。成功时可见：

```
[autopilot] analyze: generating Blueprint
[autopilot] gate: analyzing requirement
...
Agent C 发布结果：{ "agent_c_status": "submitted", ... }
```

---

## 前提条件

- **必须已配置**：`hunter/.env` 含 `DEEPSEEK_API_KEY`、`TAVILY_API_KEY`；`craftsman/.env` 含 `DEEPSEEK_API_KEY`
- **Live 上架**：额外需要 `play-sa.json`、`release.jks`、`PUBLISHER_DRY_RUN=false`
- **Docker 编译**：确认 Docker Desktop 运行中（否则走 demo 模式）
- 详情见 [play-console-setup-checklist.md](play-console-setup-checklist.md)

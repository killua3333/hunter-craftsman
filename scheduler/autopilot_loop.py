"""Windows 端自动调度核心脚本：循环启动 Craftsman 服务 → 触发 hunter autopilot。

用法：
  python autopilot_loop.py                          # 默认间隔 30 分钟，持续运行
  python autopilot_loop.py --interval 60            # 每 60 分钟一轮
  python autopilot_loop.py --once                   # 只跑一轮后退出
  python autopilot_loop.py --no-publish             # 只发现+生成，不上架

依赖：
  - Python 环境中有 craftsman 和 hunter 可执行命令
  - 或设置 PYTHONPATH 指向 craftsman/ 和 hunter/src/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn

import httpx

# ── 配置 ────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CRAFTSMAN_DIR = PROJECT_ROOT / "craftsman"
HUNTER_DIR = PROJECT_ROOT / "hunter"
CRAFTSMAN_HOST = "127.0.0.1"
CRAFTSMAN_PORT = 8791
CRAFTSMAN_HEALTH_URL = f"http://{CRAFTSMAN_HOST}:{CRAFTSMAN_PORT}/health"
DEFAULT_INTERVAL_MINUTES = 30
HEALTH_CHECK_TIMEOUT = 60  # 秒
HEALTH_POLL_INTERVAL = 2   # 秒

# 日志输出到文件 + 控制台
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "autopilot_scheduler.log"

# ── 日志 ──────────────────────────────────────────────────────────


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8", delay=True),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ── 工具函数 ──────────────────────────────────────────────────────


def _build_env() -> dict[str, str]:
    """构建包含 PYTHONPATH 和 .env 变量的环境。"""
    env = os.environ.copy()

    # 确保本地请求不受代理影响
    env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")

    # 确保 PYTHONPATH 包含两个 src 目录
    hunter_src = str(HUNTER_DIR / "src")
    craftsman_src = str(CRAFTSMAN_DIR)
    existing = env.get("PYTHONPATH", "")
    parts = [hunter_src, craftsman_src]
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)

    return env


def _run_command(
    args: list[str],
    cwd: str | Path,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """运行子进程，返回 CompletedProcess。"""
    if env is None:
        env = _build_env()
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired as exc:
        logging.error(f"命令超时 (>{timeout}s): {' '.join(args)}")
        return subprocess.CompletedProcess(args, returncode=-1, stdout=exc.stdout or "", stderr=exc.stderr or "")


# ── 服务管理 ──────────────────────────────────────────────────────

_craftsman_process: subprocess.Popen | None = None


def is_craftsman_healthy() -> bool:
    """检查 Craftsman 服务是否健康（/health 端点返回 200）。"""
    try:
        resp = httpx.get(CRAFTSMAN_HEALTH_URL, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "")
            if status in ("ok", "healthy"):
                return True
            logging.info(f"Craftsman /health 返回 status={status}, 等待就绪...")
            return False
        logging.warning(f"Craftsman /health 返回 HTTP {resp.status_code}")
        return False
    except httpx.RequestError:
        return False


def wait_for_healthy(timeout: int = HEALTH_CHECK_TIMEOUT) -> bool:
    """轮询 /health 直到服务就绪或超时。"""
    logging.info(f"等待 Craftsman 服务就绪（最多 {timeout} 秒）...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_craftsman_healthy():
            logging.info("Craftsman 服务已就绪。")
            return True
        time.sleep(HEALTH_POLL_INTERVAL)
    logging.error(f"Craftsman 服务在 {timeout} 秒内未就绪。")
    return False


def start_craftsman_server() -> bool:
    """启动 Craftsman 服务（后台子进程），返回是否成功启动。"""
    global _craftsman_process

    if _craftsman_process is not None:
        if _craftsman_process.poll() is None:
            logging.info("Craftsman 服务已在运行中。")
            return True
        _craftsman_process = None

    logging.info("启动 Craftsman 服务...")
    env = _build_env()
    args = [
        sys.executable, "-m", "craftsman.cli", "serve",
        "--host", CRAFTSMAN_HOST,
        "--port", str(CRAFTSMAN_PORT),
    ]
    try:
        _craftsman_process = subprocess.Popen(
            args,
            cwd=str(CRAFTSMAN_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # 给进程一点时间启动
        time.sleep(3)
        return wait_for_healthy()
    except Exception as exc:
        logging.error(f"启动 Craftsman 服务失败: {exc}")
        return False


def stop_craftsman_server() -> None:
    """停止 Craftsman 服务子进程。"""
    global _craftsman_process
    if _craftsman_process is None:
        return
    proc = _craftsman_process
    _craftsman_process = None
    if proc.poll() is None:
        logging.info("正在停止 Craftsman 服务...")
        # Windows: terminate, 然后 kill if needed
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logging.warning("Craftsman 未在 10 秒内停止，强制终止。")
            proc.kill()
            proc.wait(timeout=5)
    logging.info("Craftsman 服务已停止。")


# ── Hunter Autopilot 触发 ──────────────────────────────────────


def run_hunter_autopilot(
    publish: bool = True,
    timeout: float = 3600.0,
    auto_approve: bool = True,
    earnings_signal: str = "",
) -> dict[str, object]:
    """触发 hunter autopilot --publish，返回结果状态。可注入收入品类信号。"""
    args = [
        sys.executable, "-m", "hunter.main", "autopilot",
        "--base-url", f"http://{CRAFTSMAN_HOST}:{CRAFTSMAN_PORT}",
        "--timeout", str(timeout),
        "--poll-interval", "2",
    ]
    if publish:
        args.append("--publish")
    if not auto_approve:
        args.append("--no-auto-approve")

    env = _build_env()
    if earnings_signal:
        env["AUTOPILOT_EARNINGS_SIGNAL"] = earnings_signal

    logging.info(f"触发 hunter autopilot{' --publish' if publish else ''}...")
    result = _run_command(args, cwd=HUNTER_DIR, timeout=timeout + 120, env=env)

    outcome: dict[str, object] = {
        "returncode": result.returncode,
        "publish": publish,
    }

    if result.returncode == 0:
        logging.info("Autopilot 完成（returncode=0）。")
        outcome["status"] = "ok"
    elif result.returncode == 3:
        logging.warning(f"Autopilot 发布阶段非零退出 (returncode={result.returncode})。")
        outcome["status"] = "publish_issue"
    else:
        logging.error(f"Autopilot 失败 (returncode={result.returncode})。")
        outcome["status"] = "failed"

    # 抓取关键输出行
    stdout_last = result.stdout.strip().split("\n")[-5:] if result.stdout else []
    outcome["stdout_tail"] = stdout_last
    if result.stderr:
        stderr_last = result.stderr.strip().split("\n")[-3:]
        outcome["stderr_tail"] = stderr_last

    return outcome


# ── 信号处理 ──────────────────────────────────────────────────────

_shutdown_requested = False


def _signal_handler(signum: int, frame: object) -> None:
    global _shutdown_requested
    name = signal.Signals(signum).name
    logging.info(f"收到信号 {name}，准备优雅退出...")
    _shutdown_requested = True


# ── 主循环 ──────────────────────────────────────────────────────


def run_loop(
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    once: bool = False,
    publish: bool = True,
    max_rounds: int = 0,
) -> NoReturn:
    """核心循环：确保服务运行 → 触发 autopilot → 休眠 N 分钟。"""
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    round_num = 0
    exit_code = 0

    try:
        while not _shutdown_requested:
            round_num += 1
            logging.info(f"{'=' * 50}")
            logging.info(f"第 {round_num} 轮开始。")

            # 1. 确保 Craftsman 服务运行
            if not is_craftsman_healthy():
                if not start_craftsman_server():
                    logging.error("无法启动 Craftsman 服务，跳过本轮。")
                    time.sleep(60)
                    continue

            # 2. (Phase 3) Agent D — 拉取收入数据，生成品类信号
            earnings_signal = ""
            try:
                from hunter.tools.play_earnings import play_get_earnings
                earnings_raw = play_get_earnings.invoke({"months": 3})
                logging.info(f"[Accountant] 收入数据拉取完成：{earnings_raw[:200]}...")
                # 简单提取总收入，作为 AUTOPILOT_TRIGGER 的信号
                data = json.loads(earnings_raw) if isinstance(earnings_raw, str) else earnings_raw
                total_earnings = data.get("sales", {}).get("total_gross", 0)
                if total_earnings > 0:
                    earnings_signal = (
                        f"\n极收信号：累计总收入 ${total_earnings}。"
                        f"优先选择高收入同类品类方向。\n"
                    )
            except Exception as exc:
                logging.debug(f"[Accountant] 收入数据拉取跳过（可能未配置 GCS）：{exc}")
                earnings_signal = ""

            # 3. 触发 hunter autopilot（注入品类信号）
            try:
                outcome = run_hunter_autopilot(publish=publish, auto_approve=True, earnings_signal=earnings_signal)
                if outcome.get("status") == "failed":
                    exit_code = 1
            except Exception as exc:
                logging.exception(f"Autopilot 抛出异常: {exc}")

            # 4. 检查是否只跑一轮
            if once:
                logging.info("--once 模式：本轮结束，退出。")
                break

            # 5. 检查是否达到最大轮数
            if max_rounds > 0 and round_num >= max_rounds:
                logging.info(f"达到最大轮数 {max_rounds}，退出。")
                break

            # 6. 休眠
            sleep_seconds = interval_minutes * 60
            logging.info(f"本轮完成。休眠 {interval_minutes} 分钟后开始下一轮（{round_num + 1}）...")
            # 分片 sleep，便于响应 Ctrl+C
            chunk = 5
            for _ in range(sleep_seconds // chunk):
                if _shutdown_requested:
                    break
                time.sleep(chunk)

    finally:
        stop_craftsman_server()
        logging.info("调度器已退出。")

    sys.exit(exit_code)


# ── CLI ────────────────────────────────────────────────────────


def main() -> None:
    _setup_logging()

    parser = argparse.ArgumentParser(
        prog="autopilot_loop",
        description="Hunter-Craftsman 自动调度器 — 循环触发 Agent A 发现 + Agent B 生成 + Agent C 发布",
    )
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL_MINUTES,
        help=f"每轮间隔分钟数（默认 {DEFAULT_INTERVAL_MINUTES}）",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="只跑一轮后退出（不循环）",
    )
    parser.add_argument(
        "--no-publish", action="store_true",
        help="跳过 Agent C 发布步骤（只做发现+生成）",
    )
    parser.add_argument(
        "--max-rounds", type=int, default=0,
        help="最大轮数（0=无限循环）",
    )

    args = parser.parse_args()

    logging.info(f"项目根目录: {PROJECT_ROOT}")
    logging.info(f"间隔: {args.interval} 分钟 | {'单次' if args.once else '循环'} | "
                 f"发布: {'否' if args.no_publish else '是'}")
    logging.info(f"日志文件: {LOG_FILE}")

    run_loop(
        interval_minutes=args.interval,
        once=args.once,
        publish=not args.no_publish,
        max_rounds=args.max_rounds,
    )


if __name__ == "__main__":
    main()

"""CLI 入口：hunter demo | hunter chat | hunter feedback | hunter learn """

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hunter.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    build_conversation,
)
from hunter.prompts import load_system_prompt


def _configure_stdio() -> None:
    """Windows 终端默认编码可能导致中文不显示，尽量使用 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _format_message(msg) -> str:
    if isinstance(msg, SystemMessage):
        role = "system"
    elif isinstance(msg, HumanMessage):
        role = "human"
    elif isinstance(msg, AIMessage):
        role = "ai"
    elif isinstance(msg, ToolMessage):
        role = "tool"
    else:
        role = type(msg).__name__
    content = getattr(msg, "content", "") or ""
    if isinstance(msg, AIMessage) and msg.tool_calls:
        return f"[{role}] {content}\n  tool_calls={msg.tool_calls!r}"
    if isinstance(msg, ToolMessage):
        return f"[{role}] name={msg.name} id={msg.tool_call_id}\n  {content}"
    return f"[{role}] {content}"


def cmd_demo_messages() -> None:
    """打印 Message 类型示例（不调用 API）。"""
    system = load_system_prompt()
    msgs = build_conversation(system, "演示：Message 类型有哪些？")
    print("=== Message 演示（不调用模型）===\n", flush=True)
    for m in msgs:
        print(_format_message(m), flush=True)
    print(
        "\n完整 agent 运行时还会出现 AIMessage(tool_calls) 与 ToolMessage(工具结果)。",
        flush=True,
    )


_EXIT_WORDS = frozenset({"exit", "quit", "q", "bye", "退出", "/exit", "/quit"})
_MAKE_COMMAND = "/make"


def _is_make_command(text: str) -> bool:
    """仅 /make 触发 Agent B（忽略大小写与首尾空白）。"""
    return text.strip().lower() == _MAKE_COMMAND


def _print_pipeline_outcome(outcome: dict) -> int:
    """打印 A→B 编排结果，返回进程退出码。"""
    if not outcome.get("accepted"):
        print("机会未通过护栏或澄清失败。", flush=True)
        if outcome.get("answer"):
            print(outcome["answer"], flush=True)
        return 2

    if outcome.get("requirement"):
        print("\n=== requirement ===", flush=True)
        print(json.dumps(outcome["requirement"], ensure_ascii=False, indent=2), flush=True)

    feedback = outcome.get("feedback") or {}
    print("\n=== Agent B 反馈 ===", flush=True)
    print(json.dumps(feedback, ensure_ascii=False, indent=2), flush=True)
    if outcome.get("stopped"):
        print(f"\n停止原因: {outcome['stopped']}", flush=True)

    artifacts = feedback.get("artifacts") or {}
    if artifacts:
        print("\n可见 demo 产物：", flush=True)
        for key, value in artifacts.items():
            print(f"- {key}: {value}", flush=True)
    return 0


def _print_answer(result: dict, *, verbose: bool) -> None:
    print(result["answer"], flush=True)
    if verbose:
        print("\n--- 消息轨迹 ---")
        for msg in result["messages"]:
            print(_format_message(msg))
            print()


def _print_blueprint_status(
    blueprint,
    *,
    parse_error: str | None,
) -> None:
    """打印机会单是否可供 /make 使用。"""
    if blueprint is not None and blueprint.accepted:
        print(
            f"\n✓ 机会单已就绪：「{blueprint.app_name}」— 输入 /make 提交 Agent B",
            flush=True,
        )
        return
    if blueprint is not None and not blueprint.accepted:
        reason = blueprint.rejection_reason or "未说明"
        print(f"\n✗ 机会未通过护栏（accepted=false）：{reason}", flush=True)
        return
    if parse_error:
        print(f"\n✗ 未能缓存机会单（/make 暂不可用）：\n{parse_error}", flush=True)
        return
    print(
        "\n⚠ 本轮未解析到 AppOpportunityBlueprint JSON，/make 暂不可用。",
        flush=True,
    )


_REPAIR_PROMPT = (
    "你上一条助手消息中的 JSON 未通过程序校验，/make 无法使用。\n"
    "错误如下：\n{error}\n\n"
    "请**仅**输出修正后的完整 AppOpportunityBlueprint JSON（纯 JSON，无 Markdown 说明）。\n"
    "features 每项必须有 id、title、type；items 只能是字符串数组；store.keywords 必须是字符串数组。"
)


def cmd_chat(
    question: str,
    *,
    verbose: bool,
    once: bool,
    base_url: str = "http://127.0.0.1:8791",
    opportunity_id: str | None = None,
    timeout: float = 600.0,
    max_rounds: int = 3,
) -> int:
    from hunter.agents.specialist import SpecialistSession
    from hunter.orchestrator import run_blueprint_pipeline
    from hunter.schemas import AppOpportunityBlueprint, parse_blueprint

    session = SpecialistSession()
    last_blueprint: AppOpportunityBlueprint | None = None

    def run_make() -> bool:
        nonlocal last_blueprint
        if last_blueprint is None or not last_blueprint.accepted:
            print(
                "尚无可用机会单。请先与 Agent A 对话，得到 accepted=true 的 JSON 后再输入 /make。",
                file=sys.stderr,
                flush=True,
            )
            return True
        print(
            f"\n正在提交 Agent B（{last_blueprint.app_name}）…\n"
            "请确认 Craftsman 已运行: python -m craftsman.cli serve\n",
            flush=True,
        )
        try:
            outcome = run_blueprint_pipeline(
                last_blueprint,
                session=session,
                base_url=base_url,
                opportunity_id=opportunity_id,
                timeout_seconds=timeout,
                max_rounds=max_rounds,
            )
        except (ValueError, RuntimeError) as exc:
            print(f"制作失败: {exc}", file=sys.stderr, flush=True)
            return True
        if outcome.get("blueprint"):
            try:
                last_blueprint = parse_blueprint(outcome["blueprint"])
            except Exception:
                pass
        _print_pipeline_outcome(outcome)
        return True

    def _apply_turn_result(result: dict) -> None:
        nonlocal last_blueprint
        blueprint = result.get("blueprint")
        parse_error = result.get("parse_error")
        if blueprint is not None and blueprint.accepted:
            last_blueprint = blueprint
        print("\n助手:", end=" ", flush=True)
        _print_answer(result, verbose=verbose)
        _print_blueprint_status(blueprint, parse_error=parse_error)

    def run_turn(user_text: str) -> bool:
        if user_text.strip().lower() in _EXIT_WORDS:
            return False
        if not user_text.strip():
            return True
        if _is_make_command(user_text):
            return run_make()
        print("\n正在思考…", flush=True)
        try:
            result = session.send(user_text)
        except Exception as exc:
            err = str(exc)
            if "reasoning_content" in err:
                print(
                    "\n错误：当前模型为思考/推理模式，与多轮 agent 不兼容。\n"
                    "请将 config/settings.yaml 的 model.name 或 .env 的 "
                    "HUNTER_MODEL_NAME 改为 deepseek-chat 后重试。\n",
                    file=sys.stderr,
                    flush=True,
                )
                return True
            raise
        _apply_turn_result(result)
        blueprint = result.get("blueprint")
        if blueprint is None or not blueprint.accepted:
            parse_error = result.get("parse_error")
            if parse_error:
                print("\n正在根据校验错误自动修正 JSON…", flush=True)
                try:
                    repaired = session.send(_REPAIR_PROMPT.format(error=parse_error))
                except Exception:
                    raise
                _apply_turn_result(repaired)
        return True

    print(
        "Hunter 机会筛选（Agent A）— 输出 AppOpportunityBlueprint JSON\n"
        "满意后输入 /make 提交 Agent B 制作（需先启动 craftsman serve）\n"
        "（输入 exit / 退出 结束）\n",
        flush=True,
    )

    if question.strip():
        if not run_turn(question):
            return 0
        if once:
            return 0

    while True:
        try:
            user_text = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。", flush=True)
            break
        if user_text.lower() in _EXIT_WORDS:
            print("再见。", flush=True)
            break
        run_turn(user_text)

    return 0


def cmd_feedback_save(path: str) -> int:
    from hunter.feedback import save_feedback_raw

    p = Path(path)
    if not p.is_file():
        print(f"文件不存在: {p}", file=sys.stderr)
        return 1
    data = json.loads(p.read_text(encoding="utf-8"))
    out = save_feedback_raw(data)
    print(f"已保存反馈: {out}")
    return 0


def cmd_feedback_sync() -> int:
    from hunter.feedback import sync_callbacks

    result = sync_callbacks()
    if result.get("skipped"):
        print(result["reason"])
        return 1
    print(
        f"已从 {result['callbacks_dir']} 导入 {result['imported']} 条"
        f"（跳过 {result['skipped_count']}）"
    )
    return 0


def cmd_learn(*, dry_run: bool, min_count: int | None, sync_callbacks_first: bool) -> int:
    from hunter.feedback import sync_callbacks
    from hunter.learning import run_weekly_learning

    if sync_callbacks_first:
        sync_result = sync_callbacks()
        if not sync_result.get("skipped"):
            print(
                f"[sync] 导入 {sync_result['imported']} 条反馈",
                flush=True,
            )

    result = run_weekly_learning(dry_run=dry_run, min_feedback_count=min_count)
    if result.get("skipped"):
        print(result["reason"])
        return 0
    if result.get("dry_run"):
        print(f"[dry-run] 将处理 {result['pending_count']} 条 → {result['would_update']}")
        return 0
    print(f"完成 {result['week']}：处理 {result['processed_count']} 条反馈")
    print(f"  → {result['learnings_path']}")
    print(f"  报告: {result['report_path']}")
    print(f"  system 建议（人工审核）: {result['system_suggested_path']}")
    return 0


def cmd_connect_demo(
    question: str,
    *,
    base_url: str,
    opportunity_id: str | None,
    timeout: float,
    max_rounds: int,
) -> int:
    """一键联通 A→B（含 Gate 澄清循环，最多 3 轮）。"""
    from hunter.orchestrator import run_opportunity_pipeline

    if not question.strip():
        print("请提供问题文本，例如: hunter connect-demo \"做一个离线番茄钟\"", file=sys.stderr)
        return 2

    print("运行编排流水线（Agent A → Gate → 澄清 → implement）...", flush=True)
    try:
        outcome = run_opportunity_pipeline(
            question,
            base_url=base_url,
            opportunity_id=opportunity_id,
            timeout_seconds=timeout,
            max_rounds=max_rounds,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"失败: {exc}", file=sys.stderr)
        return 2

    return _print_pipeline_outcome(outcome)


def cmd_run(
    question: str,
    *,
    base_url: str,
    opportunity_id: str | None,
    timeout: float,
    max_rounds: int,
) -> int:
    """与 connect-demo 相同：完整 A→B 编排。"""
    return cmd_connect_demo(
        question,
        base_url=base_url,
        opportunity_id=opportunity_id,
        timeout=timeout,
        max_rounds=max_rounds,
    )


def main() -> None:
    _configure_stdio()

    parser = argparse.ArgumentParser(
        prog="hunter",
        description="Hunter LangChain 专精 Agent",
        epilog="示例: hunter demo | hunter chat \"你好\"",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo", help="演示 System / Human Message（不调用 API）")

    chat_p = sub.add_parser("chat", help="与专精 agent 对话（需要 DEEPSEEK_API_KEY）")
    chat_p.add_argument("question", nargs="?", default="", help="首条问题（可省略，直接进入多轮）")
    chat_p.add_argument("-v", "--verbose", action="store_true", help="打印完整消息轨迹")
    chat_p.add_argument(
        "--once",
        action="store_true",
        help="只回答一条后退出（默认持续多轮对话）",
    )
    chat_p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8791",
        help="/make 时 Craftsman API 地址",
    )
    chat_p.add_argument(
        "--opportunity-id",
        default=None,
        help="/make 时可选固定机会单 ID",
    )
    chat_p.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="/make 调用 Agent B 同步实现超时（秒）",
    )
    chat_p.add_argument(
        "--max-rounds",
        type=int,
        default=3,
        help="/make 时 needs_clarification 最多澄清轮数",
    )

    fb_p = sub.add_parser("feedback", help="管理 Agent B 反馈")
    fb_sub = fb_p.add_subparsers(dest="feedback_command", required=True)
    fb_save = fb_sub.add_parser("save", help="原样保存 Agent B JSON 到 feedback/")
    fb_save.add_argument("file", help="Craftsman 反馈 JSON 文件路径")
    fb_sub.add_parser("sync", help="从 Craftsman callbacks/ 同步终态反馈")

    learn_p = sub.add_parser("learn", help="每周学习：归纳反馈并更新 specialist_learnings.md")
    learn_p.add_argument("--dry-run", action="store_true", help="仅统计待处理条数")
    learn_p.add_argument("--min", type=int, default=None, help="最少反馈条数")
    learn_p.add_argument(
        "--sync-callbacks",
        action="store_true",
        help="学习前先同步 craftsman/callbacks",
    )

    run_p = sub.add_parser("run", help="A→B 完整编排（Gate 澄清 + implement）")
    run_p.add_argument("question", help="机会描述")
    run_p.add_argument("--base-url", default="http://127.0.0.1:8791")
    run_p.add_argument("--opportunity-id", default=None)
    run_p.add_argument("--timeout", type=float, default=180.0)
    run_p.add_argument("--max-rounds", type=int, default=3)

    connect_p = sub.add_parser(
        "connect-demo",
        help="联通 Agent A 与 Agent B，并触发可见 demo 产物生成",
    )
    connect_p.add_argument("question", help="交给 Agent A 的机会描述")
    connect_p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8791",
        help="Craftsman API 地址",
    )
    connect_p.add_argument(
        "--opportunity-id",
        default=None,
        help="可选：固定机会单 ID（默认自动生成）",
    )
    connect_p.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="调用 Agent B 同步接口超时时间（秒）",
    )
    connect_p.add_argument(
        "--max-rounds",
        type=int,
        default=3,
        help="needs_clarification 时最多澄清轮数",
    )

    args = parser.parse_args()

    if args.command == "demo":
        cmd_demo_messages()
        return

    if args.command == "feedback":
        if args.feedback_command == "save":
            raise SystemExit(cmd_feedback_save(args.file))
        if args.feedback_command == "sync":
            raise SystemExit(cmd_feedback_sync())
        return

    if args.command == "learn":
        raise SystemExit(
            cmd_learn(
                dry_run=args.dry_run,
                min_count=args.min,
                sync_callbacks_first=args.sync_callbacks,
            )
        )

    if args.command in ("connect-demo", "run"):
        question = args.question
        raise SystemExit(
            cmd_connect_demo(
                question,
                base_url=args.base_url,
                opportunity_id=args.opportunity_id,
                timeout=args.timeout,
                max_rounds=args.max_rounds,
            )
        )

    raise SystemExit(
        cmd_chat(
            args.question,
            verbose=args.verbose,
            once=args.once,
            base_url=args.base_url,
            opportunity_id=args.opportunity_id,
            timeout=args.timeout,
            max_rounds=args.max_rounds,
        )
    )


if __name__ == "__main__":
    main()

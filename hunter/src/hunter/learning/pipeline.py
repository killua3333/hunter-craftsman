"""每周闭环：sync callbacks + weekly learn。"""

from __future__ import annotations

from hunter.feedback.sync import sync_callbacks
from hunter.learning.weekly import run_weekly_learning


def main() -> int:
    print("=== 1/2 同步 Agent B callbacks → feedback/ ===", flush=True)
    sync_result = sync_callbacks()
    if sync_result.get("skipped"):
        print(sync_result["reason"], flush=True)
    else:
        print(
            f"从 {sync_result['callbacks_dir']} 导入 {sync_result['imported']} 条"
            f"（跳过 {sync_result['skipped_count']}）",
            flush=True,
        )

    print("\n=== 2/2 每周学习（更新 specialist_learnings.md）===", flush=True)
    learn_result = run_weekly_learning()
    if learn_result.get("skipped"):
        print(learn_result["reason"], flush=True)
        return 0
    print(f"完成 {learn_result['week']}：处理 {learn_result['processed_count']} 条反馈")
    print(f"  learnings: {learn_result['learnings_path']}")
    print(f"  report:    {learn_result['report_path']}")
    print(f"  建议审核:  {learn_result['system_suggested_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

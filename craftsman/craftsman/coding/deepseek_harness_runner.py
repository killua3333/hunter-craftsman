from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from .deepseek_proxy_bridge import deepseek_proxy_bridge
except ImportError:  # Executed directly by the workspace coding subprocess.
    from deepseek_proxy_bridge import deepseek_proxy_bridge


def _notification_summary(notification: Any) -> str | None:
    method = str(getattr(notification, "method", "notification"))
    payload = getattr(notification, "payload", {})
    event_type = ""
    if isinstance(payload, dict):
        event = payload.get("event")
        if isinstance(event, dict):
            event_type = str(event.get("type") or "")
    if event_type in {
        "assistant/chunk",
        "agent/inbox/spliced",
        "request/context",
        "request/header",
        "user/message",
    }:
        return None
    return json.dumps(
        {"source": "deepseek_harness", "method": method, "event_type": event_type},
        ensure_ascii=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsh-home", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", required=True)
    parser.add_argument("--max-tokens", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("DeepSeek API key is not configured", file=sys.stderr)
        return 2

    prompt = sys.stdin.read()
    if not prompt.strip():
        print("coding task is empty", file=sys.stderr)
        return 2

    try:
        from deepseek_harness import DeepSeekHarness

        args.dsh_home.mkdir(parents=True, exist_ok=True)

        def report(notification: Any) -> None:
            summary = _notification_summary(notification)
            if summary is not None:
                print(summary, flush=True)

        with deepseek_proxy_bridge() as local_base_url:
            with DeepSeekHarness(
                dsh_home=str(args.dsh_home.resolve()),
                cwd=str(Path.cwd().resolve()),
                provider="deepseek-official",
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                max_tokens=args.max_tokens,
                profile="sdk",
                api_key=api_key,
                base_url=local_base_url,
                request_timeout_seconds=args.timeout_seconds,
                env={
                    "DSH_TELEMETRY_MODE": "DISABLED",
                    "DSH_TELEMETRY_DISABLED": "1",
                },
            ) as harness:
                result = harness.run(
                    prompt,
                    session_id=args.session_id,
                    on_notification=report,
                )
        print(json.dumps({
            "source": "deepseek_harness",
            "finish_reason": result.finish_reason,
            "event_count": len(result.events),
            "final_response": result.final_response,
        }, ensure_ascii=False), flush=True)
        return 0 if result.finish_reason == "completed" else 1
    except Exception as exc:
        message = str(exc).replace(api_key, "[redacted]")
        print(f"DeepSeek Harness failed: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import logging
import time

import httpx
import uvicorn

from craftsman.api.app import create_app
from craftsman.config import settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Craftsman Agent B")
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="Start HTTP API + background worker")
    serve.add_argument("--host", default=settings.host)
    serve.add_argument("--port", type=int, default=settings.port)

    sub.add_parser("worker", help="Run worker loop only (no HTTP)")

    publish = sub.add_parser("publish", help="Fast-path: build and publish to Google Play (skips LLM)")
    publish.add_argument("name", nargs="?", default="Hello World", help="App display name")
    publish.add_argument("--track", default="internal", choices=["internal", "alpha", "beta", "production"])
    publish.add_argument("--package", default=None, help="Override package name")
    publish.add_argument("--timeout", type=int, default=600, help="Poll timeout seconds")
    publish.add_argument("--skip-serve", action="store_true", help="Expect server already running on 127.0.0.1:8791")

    args = parser.parse_args()
    if args.cmd == "serve":
        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    elif args.cmd == "worker":
        from craftsman.worker import BackgroundWorker

        w = BackgroundWorker()
        w.start()
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            w.stop()
    elif args.cmd == "publish":
        _cmd_publish(args)
    else:
        parser.print_help()


def _cmd_publish(args) -> None:
    """Fast-path publish flow: prepare project → build → upload."""
    import sys, subprocess, threading
    from craftsman.publisher.fast_publisher import prepare_fast_project, build_release_handoff

    package = args.package or settings.google_play_package_name or "com.craftsman.app"
    logger = logging.getLogger("craftsman.publish")

    # 1. Prepare project
    logger.info("preparing project: name=%r package=%s track=%s", args.name, package, args.track)
    run_id = prepare_fast_project(args.name)
    handoff = build_release_handoff(run_id)

    # 2. Start server if needed
    server_proc = None
    if not args.skip_serve:
        logger.info("starting background server...")
        server_proc = subprocess.Popen(
            [sys.executable, "-m", "craftsman.cli", "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(4)  # wait for startup

    BASE = "http://127.0.0.1:8791"

    client = httpx.Client(timeout=30)

    # 3. Prepare release
    logger.info("calling /v1/releases/prepare...")
    prep = client.post(f"{BASE}/v1/releases/prepare", json=handoff)
    prep_data = prep.json()
    if not prep_data.get("accepted"):
        logger.error("prepare rejected: policy=%s", prep_data.get("policy"))
        _cleanup(server_proc)
        sys.exit(1)

    # 4. Submit
    logger.info("calling /v1/releases/{}/submit...", run_id)
    sub_resp = client.post(f"{BASE}/v1/releases/{run_id}/submit", json={})
    sub_data = sub_resp.json()
    if sub_data.get("status") != "submitting":
        logger.error("submit failed: %s", sub_data)
        _cleanup(server_proc)
        sys.exit(1)

    # 5. Poll
    logger.info("polling release status (timeout=%ds)...", args.timeout)
    start = time.monotonic()
    while (time.monotonic() - start) < args.timeout:
        try:
            r = client.get(f"{BASE}/v1/releases/{run_id}")
            data = r.json()
        except Exception:
            time.sleep(10)
            continue

        st = data.get("status")
        agent_c = data.get("agent_c_status") or "?"

        if st in ("published", "dry_run_complete"):
            logger.info("*** PUBLISHED to %s track! ***", args.track)
            logger.info("   versionCode will be on your Play Console: https://play.google.com/console/")
            _cleanup(server_proc)
            sys.exit(0)

        if st in ("failed", "dead_letter"):
            state = data.get("state") or {}
            details_raw = state.get("details_json")
            reasons = []
            if details_raw:
                import json
                details = json.loads(details_raw)
                ac = details.get("agent_c") or {}
                reasons = ac.get("reasons") or []
            logger.error("FAILED: status=%s reasons=%s", st, reasons[:3])
            _cleanup(server_proc)
            sys.exit(1)

        logger.info("  [%s] agent_c=%s", st, agent_c)
        time.sleep(15)

    logger.error("TIMEOUT after %ds", args.timeout)
    _cleanup(server_proc)
    sys.exit(1)


def _cleanup(proc) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait(timeout=5)

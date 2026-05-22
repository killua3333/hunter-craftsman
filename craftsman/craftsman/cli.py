import argparse
import logging

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

    args = parser.parse_args()
    if args.cmd == "serve":
        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    elif args.cmd == "worker":
        from craftsman.worker import BackgroundWorker

        w = BackgroundWorker()
        w.start()
        try:
            import time

            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            w.stop()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

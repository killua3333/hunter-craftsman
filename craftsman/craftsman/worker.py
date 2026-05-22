from __future__ import annotations

import logging
import threading
import time

from craftsman.config import settings
from craftsman.orchestrator.pipeline import run_implementation
from craftsman.store.db import RunStore

logger = logging.getLogger(__name__)


class BackgroundWorker:
    def __init__(self, store: RunStore | None = None) -> None:
        self.store = store or RunStore()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="craftsman-worker", daemon=True)
        self._thread.start()
        logger.info("Background worker started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def _loop(self) -> None:
        while not self._stop.is_set():
            run_id = self.store.claim_next_job()
            if not run_id:
                time.sleep(settings.poll_interval_seconds)
                continue
            try:
                run_implementation(self.store, run_id)
            except Exception:
                logger.exception("job failed: %s", run_id)
            finally:
                self.store.complete_job(run_id)

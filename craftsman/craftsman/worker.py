"""Background job worker for implementation and release submit queues."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from craftsman.config import settings
from craftsman.orchestrator.failure_taxonomy import classify_runtime_exception
from craftsman.orchestrator.pipeline import WorkerStopRequested, run_implementation
from craftsman.publisher.models import PublisherStatus
from craftsman.publisher.orchestrator import run_android_release
from craftsman.store.db import RunStore

logger = logging.getLogger(__name__)


class BackgroundWorker:
    def __init__(self, store: RunStore | None = None) -> None:
        self.store = store or RunStore()
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if any(t.is_alive() for t in self._threads):
            return
        self._stop.clear()
        count = max(int(settings.job_worker_count), 1)
        self._threads = []
        for idx in range(count):
            thread = threading.Thread(
                target=self._loop,
                name=f"craftsman-worker-{idx}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)
        logger.info("Background worker started threads=%s", count)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=30.0)
        self._threads.clear()

    def _loop(self) -> None:
        while not self._stop.is_set():
            claim = self.store.claim_next_job(
                lease_seconds=settings.job_lease_seconds,
                worker_id=self.worker_id,
            )
            if claim:
                self._process_implementation(claim["run_id"], claim["lease_token"])
                continue
            release_claim = self.store.claim_next_release_job(
                lease_seconds=settings.job_lease_seconds,
                worker_id=self.worker_id,
            )
            if release_claim:
                self._process_release(release_claim["release_id"], release_claim["lease_token"])
                continue
            time.sleep(settings.poll_interval_seconds)

    def _process_implementation(self, run_id: str, lease_token: str) -> None:
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._lease_heartbeat,
            args=(run_id, lease_token, heartbeat_stop, "implementation"),
            daemon=True,
        )
        heartbeat.start()
        try:
            run_implementation(self.store, run_id, should_stop=self._stop.is_set)
            action = self.store.complete_job(
                run_id,
                worker_id=self.worker_id,
                lease_token=lease_token,
            )
            if action != "done":
                logger.warning(
                    "complete skipped due to stale ownership: run_id=%s worker_id=%s",
                    run_id,
                    self.worker_id,
                )
        except WorkerStopRequested:
            action = self.store.fail_job(
                run_id,
                error_message="worker shutdown requested",
                retryable=True,
                worker_id=self.worker_id,
                lease_token=lease_token,
            )
            logger.info("job requeued for shutdown: run_id=%s action=%s", run_id, action)
        except Exception as exc:
            taxonomy = classify_runtime_exception(exc)
            action = self.store.fail_job(
                run_id,
                error_message=f"{taxonomy['category']}: {exc}",
                retryable=bool(taxonomy["retryable"]),
                worker_id=self.worker_id,
                lease_token=lease_token,
            )
            logger.exception("job failed: run_id=%s action=%s category=%s", run_id, action, taxonomy["category"])
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=1.0)

    def _process_release(self, release_id: str, lease_token: str) -> None:
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._lease_heartbeat,
            args=(release_id, lease_token, heartbeat_stop, "release"),
            daemon=True,
        )
        heartbeat.start()
        try:
            state = self.store.get_release_state(release_id) or {}
            details: dict[str, Any] = state.get("details") if isinstance(state.get("details"), dict) else {}
            handoff = details.get("release_handoff")
            if not isinstance(handoff, dict):
                raise RuntimeError("release handoff missing in release state")

            policy = self.store.get_release_policy_check(release_id)
            approval = self.store.get_release_approval(release_id)
            agent_result = run_android_release(handoff, release_id=release_id)
            agent_status = str(agent_result.get("agent_c_status") or "failed")
            if agent_status == PublisherStatus.SUBMITTED.value:
                final_status = "published"
            elif agent_status == PublisherStatus.DRY_RUN_COMPLETE.value:
                final_status = "dry_run_complete"
            else:
                final_status = "failed"

            self.store.upsert_release_state(
                release_id,
                status=final_status,
                details={
                    **details,
                    "policy": policy,
                    "approval": approval,
                    "platform_target": details.get("platform_target") or "android",
                    "agent_c": agent_result,
                },
                updated_by="agent_c",
            )
            self.store.complete_release_job(
                release_id,
                worker_id=self.worker_id,
                lease_token=lease_token,
            )
            self.store.append_audit_log(
                event_type="release_submit_completed",
                release_id=release_id,
                actor="agent_c",
                payload={"agent_c_status": agent_status, "platform_target": details.get("platform_target")},
            )
        except Exception as exc:
            taxonomy = classify_runtime_exception(exc)
            self.store.fail_release_job(
                release_id,
                error_message=f"{taxonomy['category']}: {exc}",
                retryable=bool(taxonomy["retryable"]),
                worker_id=self.worker_id,
                lease_token=lease_token,
            )
            state = self.store.get_release_state(release_id) or {}
            details: dict[str, Any] = state.get("details") if isinstance(state.get("details"), dict) else {}
            self.store.upsert_release_state(
                release_id,
                status="failed",
                details={
                    **details,
                    "message": str(exc),
                    "category": taxonomy["category"],
                },
                updated_by="agent_c",
            )
            logger.exception("release job failed: release_id=%s", release_id)
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=1.0)

    def _lease_heartbeat(
        self,
        job_id: str,
        lease_token: str,
        stop: threading.Event,
        job_kind: str,
    ) -> None:
        interval = max(settings.job_lease_seconds // 3, 5)
        while not stop.wait(interval):
            if job_kind == "release":
                renewed = self.store.renew_release_lease(
                    job_id,
                    worker_id=self.worker_id,
                    lease_token=lease_token,
                    lease_seconds=settings.job_lease_seconds,
                )
            else:
                renewed = self.store.renew_lease(
                    job_id,
                    worker_id=self.worker_id,
                    lease_token=lease_token,
                    lease_seconds=settings.job_lease_seconds,
                )
            if not renewed:
                logger.warning("lease renewal failed: job_id=%s worker_id=%s", job_id, self.worker_id)
                return

"""Hunter orchestration bridge to Craftsman Agent C (Publisher)."""

from __future__ import annotations

import time
from typing import Any

from hunter.integrations.craftsman import _http_json, _with_retry

TERMINAL_RELEASE_STATUSES = frozenset(
    {
        "published",
        "dry_run_complete",
        "failed",
        "platform_unavailable",
        "prepare_rejected",
        "approval_required",
    }
)


def prepare_release(
    handoff: dict[str, Any],
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Register release handoff and run policy checks."""
    url = f"{base_url.rstrip('/')}/v1/releases/prepare"
    return _with_retry(
        lambda: _http_json(url=url, body=handoff, method="POST", timeout_seconds=timeout_seconds)
    )


def approve_release(
    release_id: str,
    *,
    approved_by: str = "hunter-auto",
    note: str | None = "auto-approved for publish pipeline",
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/v1/releases/{release_id}/approve"
    body = {"approved_by": approved_by, "decision": "approved", "note": note}
    return _with_retry(
        lambda: _http_json(url=url, body=body, method="POST", timeout_seconds=timeout_seconds)
    )


def submit_release(
    release_id: str,
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Trigger Agent C build/sign/upload."""
    url = f"{base_url.rstrip('/')}/v1/releases/{release_id}/submit"
    return _with_retry(
        lambda: _http_json(url=url, body=None, method="POST", timeout_seconds=timeout_seconds)
    )


def get_release_status(
    release_id: str,
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/v1/releases/{release_id}"
    return _with_retry(
        lambda: _http_json(url=url, body=None, method="GET", timeout_seconds=timeout_seconds)
    )


def wait_for_release_completion(
    release_id: str,
    *,
    base_url: str = "http://127.0.0.1:8791",
    timeout_seconds: float = 1800.0,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    """Poll release status until terminal state or timeout."""
    deadline = time.monotonic() + max(timeout_seconds, 1.0)
    last: dict[str, Any] = {"release_id": release_id, "status": "unknown"}
    while time.monotonic() < deadline:
        last = get_release_status(release_id, base_url=base_url, timeout_seconds=30.0)
        status = str(last.get("status") or "").strip().lower()
        if status in TERMINAL_RELEASE_STATUSES:
            return last
        time.sleep(max(poll_interval_seconds, 0.2))
    last["poll_timed_out"] = True
    return last


def _play_console_fields(*sources: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Resolve setup sheet from submit response, poll GET, or nested agent_c."""
    setup_path: str | None = None
    setup_sheet: str | None = None
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source.get("setup_sheet"):
            setup_sheet = str(source["setup_sheet"])
        if source.get("play_console_setup_path"):
            setup_path = str(source["play_console_setup_path"])
        nested = source.get("agent_c")
        if isinstance(nested, dict):
            setup_sheet = setup_sheet or (str(nested["setup_sheet"]) if nested.get("setup_sheet") else None)
            setup_path = setup_path or (
                str(nested["play_console_setup_path"]) if nested.get("play_console_setup_path") else None
            )
    return setup_path, setup_sheet


def run_publish_pipeline(
    feedback: dict[str, Any],
    *,
    base_url: str = "http://127.0.0.1:8791",
    auto_approve: bool = True,
    approved_by: str = "hunter-auto",
    timeout_seconds: float = 1800.0,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    """
    Agent C pipeline: prepare → (optional approve) → submit.

    Expects Agent B feedback with release_handoff and run_id.
    """
    handoff = feedback.get("release_handoff")
    if not isinstance(handoff, dict):
        raise RuntimeError("missing release_handoff in Agent B feedback")

    run_id = str(feedback.get("run_id") or handoff.get("run_id") or "")
    release_id = str(handoff.get("release_id") or (f"rel-{run_id}" if run_id else "rel-unknown"))
    payload = {**handoff, "release_id": release_id}

    prepare = prepare_release(payload, base_url=base_url, timeout_seconds=60.0)
    if not prepare.get("accepted"):
        return {
            "release_id": release_id,
            "publish_status": "prepare_rejected",
            "prepare": prepare,
        }

    approval = None
    if prepare.get("approval_required") and auto_approve:
        approval = approve_release(
            release_id,
            approved_by=approved_by,
            base_url=base_url,
            timeout_seconds=30.0,
        )
    elif prepare.get("approval_required") and not auto_approve:
        return {
            "release_id": release_id,
            "publish_status": "approval_required",
            "prepare": prepare,
        }

    submit = submit_release(release_id, base_url=base_url, timeout_seconds=60.0)
    publish_status = str(submit.get("status") or submit.get("agent_c_status") or "unknown")
    if publish_status.lower() in TERMINAL_RELEASE_STATUSES:
        final = submit
    else:
        final = wait_for_release_completion(
            release_id,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
    final_status = str(final.get("status") or publish_status)
    setup_path, setup_sheet = _play_console_fields(submit, final)
    result = {
        "release_id": release_id,
        "publish_status": final_status,
        "final_status": final_status,
        "prepare": prepare,
        "approval": approval,
        "submit": submit,
        "release_poll": final,
        "play_console_setup_path": setup_path,
        "setup_sheet": setup_sheet,
    }
    if final.get("poll_timed_out"):
        result["poll_timed_out"] = True
    return result

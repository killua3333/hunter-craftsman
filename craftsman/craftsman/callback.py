from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx

from craftsman.config import settings
from craftsman.models import CraftsmanFeedback

logger = logging.getLogger(__name__)


def _validate_webhook_mandatory_mode() -> None:
    if not settings.webhook_mandatory:
        return
    if not settings.webhook_url:
        raise RuntimeError("webhook mandatory mode requires WEBHOOK_URL")
    if not settings.resolved_webhook_secret():
        raise RuntimeError("webhook mandatory mode requires WEBHOOK_SECRET for signed delivery")


def deliver_feedback(feedback: CraftsmanFeedback) -> None:
    payload = feedback.to_agent_a_dict()
    _validate_webhook_mandatory_mode()
    settings.callback_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{feedback.opportunity_id}_r{feedback.revision}_{feedback.agent_b_status}.json"
    path = settings.callback_dir / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote callback file: %s", path)

    if settings.webhook_url:
        _post_webhook(payload, required=settings.webhook_mandatory)


def _post_webhook(payload: dict, *, required: bool) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secret = settings.resolved_webhook_secret()
    if secret:
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Craftsman-Signature"] = sig
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(settings.webhook_url, content=body, headers=headers)
            resp.raise_for_status()
        logger.info("Webhook delivered to %s", settings.webhook_url)
    except Exception as exc:
        if required:
            raise RuntimeError(f"mandatory webhook delivery failed: {exc}") from exc
        logger.warning("Webhook delivery failed: %s", exc)

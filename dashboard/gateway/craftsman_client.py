"""Thin async client for Craftsman API with proper error mapping."""

from __future__ import annotations

import logging
import sys
from typing import Any

import httpx
from fastapi import HTTPException

from settings import settings

logger = logging.getLogger("dashboard.craftsman")


class CraftsmanUpstreamError(HTTPException):
    """Surface upstream Craftsman errors as 502 with structured detail."""

    def __init__(self, message: str, *, status: int = 502, code: str = "craftsman_upstream"):
        super().__init__(status_code=status, detail={"code": code, "message": message})


def _headers() -> dict[str, str]:
    headers = {"X-Contract-Version": settings.craftsman_contract_version}
    token = settings.craftsman_api_token or _resolve_craftsman_token()
    if token:
        headers["X-API-Token"] = token
    return headers


def _resolve_craftsman_token() -> str | None:
    try:
        root = settings.workspace_root.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from craftsman.config import settings as cs  # noqa: PLC0415

        return cs.resolved_api_token()
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not resolve craftsman token: %s", exc)
        return None


async def craftsman_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Issue a request to Craftsman, returning parsed JSON or raising HTTPException."""
    url = f"{settings.craftsman_base_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                headers=_headers(),
                params=params,
                json=json_body,
            )
    except httpx.ConnectError as exc:
        raise CraftsmanUpstreamError(
            f"无法连接 Craftsman {settings.craftsman_base_url}: {exc}",
            code="craftsman_unreachable",
        ) from exc
    except httpx.TimeoutException as exc:
        raise CraftsmanUpstreamError(
            f"Craftsman 请求超时: {path}",
            code="craftsman_timeout",
        ) from exc

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": response.text[:200]})
    if response.status_code == 401:
        raise CraftsmanUpstreamError("API token 无效或缺失", status=401, code="unauthorized")
    if response.status_code >= 400:
        raise CraftsmanUpstreamError(
            f"craftsman {response.status_code}: {response.text[:300]}",
            code="craftsman_error",
        )

    try:
        return response.json()
    except ValueError as exc:
        raise CraftsmanUpstreamError(f"非 JSON 响应: {exc}") from exc


async def craftsman_health() -> bool:
    try:
        await craftsman_request("GET", "/health", timeout=3.0)
        return True
    except HTTPException:
        return False

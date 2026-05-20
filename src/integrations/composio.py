"""Thin wrapper over the Composio tool-execution REST API.

Composio (https://composio.dev) is an integration platform that holds the
OAuth connection to Instagram and exposes the Instagram Graph API as callable
"tools". Auth is via a project API key (COMPOSIO_API_KEY). A specific
connected account is targeted via COMPOSIO_INSTAGRAM_ACCOUNT_ID.

Docs: POST https://backend.composio.dev/api/v3/tools/execute/{tool_slug}
"""

from __future__ import annotations

from typing import Any

import httpx

from src.config import settings

API_ROOT = "https://backend.composio.dev/api/v3"


def _headers() -> dict[str, str]:
    if not settings.composio_api_key:
        raise RuntimeError("COMPOSIO_API_KEY не задан в Railway")
    return {
        "x-api-key": settings.composio_api_key,
        "Content-Type": "application/json",
    }


async def execute(
    slug: str,
    arguments: dict[str, Any],
    connected_account_id: str | None = None,
) -> dict[str, Any]:
    """Execute a Composio tool by slug; return the tool's `data` payload.

    Raises RuntimeError on transport or Composio-level failure.
    """
    body: dict[str, Any] = {"arguments": arguments}
    account = connected_account_id or settings.composio_instagram_account_id
    if account:
        body["connected_account_id"] = account

    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            f"{API_ROOT}/tools/execute/{slug}",
            headers=_headers(),
            json=body,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Composio API {r.status_code}: {r.text[:300]}")
        payload = r.json()

    # v3 execute wraps the tool output: {data, successful, error}.
    # Be tolerant if the wrapper is absent.
    if isinstance(payload, dict) and payload.get("successful") is False:
        raise RuntimeError(str(payload.get("error") or "Composio вернул ошибку"))
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        return data
    return payload if isinstance(payload, dict) else {}

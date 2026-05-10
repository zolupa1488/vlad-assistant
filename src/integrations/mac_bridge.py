"""HTTP client to the Mac Bridge — a small FastAPI server that wraps Claude Code on Vladimir's laptop."""

from __future__ import annotations

import httpx

from src.config import settings


async def run_on_mac(task: str, timeout: float | None = None) -> dict:
    if not settings.mac_bridge_url or not settings.mac_bridge_token:
        raise RuntimeError(
            "Mac Bridge не настроен. Нужны MAC_BRIDGE_URL и MAC_BRIDGE_TOKEN в Railway."
        )

    timeout = timeout or settings.mac_bridge_timeout
    headers = {
        "Authorization": f"Bearer {settings.mac_bridge_token}",
        "Content-Type": "application/json",
    }
    url = settings.mac_bridge_url.rstrip("/") + "/run"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json={"task": task}, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def health_check() -> dict:
    if not settings.mac_bridge_url:
        return {"ok": False, "reason": "MAC_BRIDGE_URL not set"}
    url = settings.mac_bridge_url.rstrip("/") + "/health"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(url)
            return {"ok": resp.status_code == 200, "status": resp.status_code}
        except Exception as e:
            return {"ok": False, "reason": f"{type(e).__name__}: {e}"}

"""Thin wrapper over Figma REST API (read-only).

Auth is via Personal Access Token (FIGMA_TOKEN env var). Figma doesn't have
write access via REST — design edits are plugin-only inside Figma — so all
of these operations are reads/exports.
"""

from __future__ import annotations

import re

import httpx

from src.config import settings

API_ROOT = "https://api.figma.com/v1"

_FILE_KEY_RE = re.compile(r"figma\.com/(?:design|file|proto)/([A-Za-z0-9]+)")


def extract_file_key(url_or_key: str) -> str:
    """Accept either a full Figma URL or a bare file_key, return the file_key."""
    s = url_or_key.strip()
    m = _FILE_KEY_RE.search(s)
    if m:
        return m.group(1)
    return s


def _headers() -> dict[str, str]:
    if not settings.figma_token:
        raise RuntimeError("FIGMA_TOKEN не задан в Railway")
    return {"X-Figma-Token": settings.figma_token}


async def get_file(url_or_key: str, depth: int | None = 2) -> dict:
    """Fetch the document tree of a Figma file. `depth` limits recursion."""
    file_key = extract_file_key(url_or_key)
    params: dict = {}
    if depth is not None:
        params["depth"] = depth
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{API_ROOT}/files/{file_key}", headers=_headers(), params=params
        )
        r.raise_for_status()
        return r.json()


async def export_images(
    url_or_key: str,
    node_ids: list[str],
    format: str = "png",
    scale: float = 2.0,
) -> dict:
    """Ask Figma to render the listed nodes and return URLs to download."""
    file_key = extract_file_key(url_or_key)
    params = {
        "ids": ",".join(node_ids),
        "format": format,
        "scale": str(scale),
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(
            f"{API_ROOT}/images/{file_key}", headers=_headers(), params=params
        )
        r.raise_for_status()
        return r.json()  # {"images": {node_id: image_url}}


async def get_comments(url_or_key: str) -> dict:
    file_key = extract_file_key(url_or_key)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{API_ROOT}/files/{file_key}/comments", headers=_headers()
        )
        r.raise_for_status()
        return r.json()


async def get_file_versions(url_or_key: str) -> dict:
    file_key = extract_file_key(url_or_key)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{API_ROOT}/files/{file_key}/versions", headers=_headers()
        )
        r.raise_for_status()
        return r.json()

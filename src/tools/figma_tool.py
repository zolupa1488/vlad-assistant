"""Claude-side tools for Figma (read + export)."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import httpx

from src.integrations import figma as fg

OUTPUT_DIR = os.environ.get("FILES_OUTPUT_DIR", "/app/data/files")
_MAX_FRAMES_PER_PAGE = 30


def _summarise_file(data: dict) -> dict:
    pages: list[dict[str, Any]] = []
    for page in data.get("document", {}).get("children", []):
        frames = []
        for child in page.get("children", []) or []:
            frames.append(
                {
                    "node_id": child.get("id"),
                    "name": child.get("name"),
                    "type": child.get("type"),
                }
            )
            if len(frames) >= _MAX_FRAMES_PER_PAGE:
                break
        pages.append(
            {
                "node_id": page.get("id"),
                "name": page.get("name"),
                "frames_count": len(page.get("children", []) or []),
                "frames": frames,
            }
        )
    return {
        "name": data.get("name"),
        "lastModified": data.get("lastModified"),
        "thumbnailUrl": data.get("thumbnailUrl"),
        "pages": pages,
    }


async def figma_get_file(url_or_key: str) -> str:
    """Fetch a Figma file's structure: pages and top-level frames with node_ids
    (for use with figma_export_image)."""
    try:
        data = await fg.get_file(url_or_key, depth=2)
    except Exception as e:
        return f"Не получилось прочитать Figma-файл: {type(e).__name__}: {e}"
    return json.dumps(_summarise_file(data), ensure_ascii=False, indent=2)


async def figma_export_image(
    url_or_key: str,
    node_id: str,
    format: str = "png",
    scale: float = 2.0,
) -> str:
    """Render a Figma node (frame, group, component) as image and ship it
    to Telegram. Allowed formats: png, jpg, svg, pdf."""
    try:
        result = await fg.export_images(url_or_key, [node_id], format=format, scale=scale)
    except Exception as e:
        return f"Не получилось экспортировать: {type(e).__name__}: {e}"

    image_url = (result.get("images") or {}).get(node_id)
    if not image_url:
        return f"Figma не вернула картинку для node_id={node_id}"

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fname = f"figma-{uuid.uuid4().hex[:8]}.{format}"
    path = os.path.join(OUTPUT_DIR, fname)
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(image_url)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)

    kind = "image" if format in {"png", "jpg", "jpeg"} else "document"
    return json.dumps(
        {
            "ok": True,
            "kind": kind,
            "file_path": path,
            "file_name": fname,
            "size_bytes": os.path.getsize(path),
        },
        ensure_ascii=False,
    )


async def figma_get_comments(url_or_key: str) -> str:
    try:
        data = await fg.get_comments(url_or_key)
    except Exception as e:
        return f"Не получилось получить комментарии: {type(e).__name__}: {e}"

    items = []
    for c in data.get("comments", []) or []:
        items.append(
            {
                "id": c.get("id"),
                "user": (c.get("user") or {}).get("handle"),
                "message": c.get("message"),
                "created_at": c.get("created_at"),
                "resolved": c.get("resolved_at") is not None,
            }
        )
    if not items:
        return "(в файле нет комментариев)"
    return json.dumps(items, ensure_ascii=False, indent=2)

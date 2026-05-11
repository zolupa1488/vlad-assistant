"""Image generation via OpenRouter (Gemini 2.5 Flash Image / 'nano-banana').

OpenRouter exposes Gemini's image generation behind the same chat-completions
API. The model returns generated images either as base64 in
`response.choices[0].message.images[].image_url.url` or as a regular URL.

We save the output PNG to /app/data/files/ and hand it back to the registry
via the standard file-collector contract (kind="image"), so handlers ship
it as a Telegram photo.
"""

from __future__ import annotations

import base64
import json
import os
import re
import uuid

import httpx
from loguru import logger
from openai import AsyncOpenAI

from src.config import settings

OUTPUT_DIR = os.environ.get("FILES_OUTPUT_DIR", "/app/data/files")
_DATA_URL_RE = re.compile(r"^data:image/[\w+.-]+;base64,(.+)$", re.IGNORECASE)


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": "https://github.com/zolupa1488/vlad-assistant",
            "X-Title": "Vlad Assistant",
        },
    )


async def _materialize_image(payload: str) -> bytes:
    """`payload` is either a data: URL with base64, or a plain https:// URL."""
    m = _DATA_URL_RE.match(payload)
    if m:
        return base64.b64decode(m.group(1))
    if payload.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.get(payload)
            r.raise_for_status()
            return r.content
    # fall-through — maybe it's raw base64
    try:
        return base64.b64decode(payload)
    except Exception as e:
        raise RuntimeError(f"unrecognized image payload format: {e}") from e


async def generate_image(prompt: str) -> str:
    """Generate an image from a text prompt. Result is shipped as a file via the
    registry's file collector (kind='image'). Returns a JSON status string."""
    if not settings.image_gen_enabled:
        return json.dumps(
            {"ok": False, "reason": "image generation disabled in config"},
            ensure_ascii=False,
        )

    client = _client()
    try:
        # OpenRouter accepts both `extra_body` and direct kwargs; we use
        # extra_body to stay compatible with the OpenAI SDK's type checks.
        response = await client.chat.completions.create(
            model=settings.image_model,
            messages=[{"role": "user", "content": prompt}],
            extra_body={"modalities": ["image", "text"]},
        )
    except Exception as e:
        logger.exception("image gen call failed")
        return json.dumps(
            {"ok": False, "reason": f"{type(e).__name__}: {e}"},
            ensure_ascii=False,
        )

    msg = response.choices[0].message
    # OpenRouter returns images on .images (list of {image_url: {url: ...}}).
    images = getattr(msg, "images", None) or []
    if not images and isinstance(getattr(msg, "model_extra", None), dict):
        images = msg.model_extra.get("images") or []

    if not images:
        # Some models inline the base64 in `content` — last-resort scan.
        content = getattr(msg, "content", "") or ""
        if "data:image" in content:
            images = [{"image_url": {"url": content}}]

    if not images:
        return json.dumps(
            {
                "ok": False,
                "reason": "the model returned no image — probably the prompt was rejected",
                "text": (msg.content or "")[:500],
            },
            ensure_ascii=False,
        )

    # Take the first image.
    first = images[0]
    url_holder = first.get("image_url") if isinstance(first, dict) else None
    payload: str | None = None
    if isinstance(url_holder, dict):
        payload = url_holder.get("url")
    elif isinstance(first, str):
        payload = first
    if not payload:
        return json.dumps(
            {"ok": False, "reason": "image payload was empty"}, ensure_ascii=False
        )

    try:
        data = await _materialize_image(payload)
    except Exception as e:
        return json.dumps(
            {"ok": False, "reason": f"download failed: {type(e).__name__}: {e}"},
            ensure_ascii=False,
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fname = f"img-{uuid.uuid4().hex[:8]}.png"
    path = os.path.join(OUTPUT_DIR, fname)
    with open(path, "wb") as f:
        f.write(data)

    return json.dumps(
        {
            "ok": True,
            "kind": "image",
            "file_path": path,
            "file_name": fname,
            "size_bytes": os.path.getsize(path),
            "prompt": prompt,
        },
        ensure_ascii=False,
    )

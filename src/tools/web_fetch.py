"""web_fetch tool — read a URL and return readable text."""

from __future__ import annotations

import httpx
from selectolax.parser import HTMLParser

_MAX_CHARS = 8000
_TIMEOUT = 15.0


async def web_fetch(url: str) -> str:
    """Return up to ~8K chars of readable text extracted from a URL."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=_TIMEOUT,
        headers={
            "User-Agent": (
                "VladAssistant/0.2 (+https://t.me/vladimirov_pa_bot)"
            ),
        },
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "").lower()
        if "html" in ctype or "<html" in r.text[:200].lower():
            tree = HTMLParser(r.text)
            for tag in ("script", "style", "nav", "footer", "header", "noscript", "iframe"):
                for node in tree.css(tag):
                    node.decompose()
            body = tree.body or tree.root
            text = body.text(separator="\n") if body else r.text
        else:
            text = r.text

    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return text[:_MAX_CHARS]

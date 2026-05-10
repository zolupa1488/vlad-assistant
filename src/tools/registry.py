"""Tool registry — JSON schemas + dispatcher."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from loguru import logger

from src.tools.web_fetch import web_fetch

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": (
                "Fetch the readable text content of a public URL. "
                "Use when the user provides a link or you need to read web content for context. "
                "Returns up to ~8K characters of cleaned text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch (with or without http/https prefix).",
                    },
                },
                "required": ["url"],
            },
        },
    },
]


_DISPATCH: dict[str, Callable[..., Awaitable[str]]] = {
    "web_fetch": web_fetch,
}


async def execute_tool(name: str, args_json: str) -> str:
    fn = _DISPATCH.get(name)
    if fn is None:
        return f"unknown tool: {name}"
    try:
        args = json.loads(args_json) if args_json else {}
    except Exception as e:
        return f"invalid arguments JSON: {e}"
    try:
        return await fn(**args)
    except Exception as e:
        logger.exception("tool {} failed", name)
        return f"error executing {name}: {type(e).__name__}: {e}"

"""Tool registry — JSON schemas + dispatcher."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from loguru import logger

from src.tools.google_sheets_tool import (
    create_google_sheet,
    find_google_sheet,
    read_google_sheet,
    write_google_sheet,
)
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
    {
        "type": "function",
        "function": {
            "name": "find_google_sheet",
            "description": (
                "Search Vladimir's Google Drive for spreadsheets whose name contains `query`. "
                "ALWAYS call this first to get the spreadsheet_id before reading or writing. "
                "Returns up to 8 matches with id, name, url, owner, and modifiedTime."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Substring of the spreadsheet name (case-insensitive).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_google_sheet",
            "description": (
                "Read a range from a spreadsheet. Output is TSV (tabs between cells, newlines between rows), "
                "capped at 100 rows. Use after find_google_sheet to get the id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {
                        "type": "string",
                        "description": "A1 notation, e.g. 'Sheet1!A1:F50' or 'A1:Z200'. Default: 'A1:Z200'.",
                    },
                },
                "required": ["spreadsheet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_google_sheet",
            "description": (
                "Write a block of values into a spreadsheet range. "
                "Only works on sheets where Vladimir is editor/owner."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {
                        "type": "string",
                        "description": "Top-left A1 cell to start, e.g. 'Sheet1!A1' or 'B2'.",
                    },
                    "values_csv": {
                        "type": "string",
                        "description": (
                            "Rows separated by newline, cells separated by TAB (preferred) or comma. "
                            "Example: 'name\\tvalue\\nfoo\\t10\\nbar\\t20'."
                        ),
                    },
                },
                "required": ["spreadsheet_id", "range", "values_csv"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_google_sheet",
            "description": (
                "Create a new spreadsheet in Vladimir's Drive (he becomes owner). "
                "Returns its id and url."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Spreadsheet title."},
                    "headers_csv": {
                        "type": "string",
                        "description": "Optional comma-separated header row to write to A1.",
                    },
                },
                "required": ["title"],
            },
        },
    },
]


_DISPATCH: dict[str, Callable[..., Awaitable[str]]] = {
    "web_fetch": web_fetch,
    "find_google_sheet": find_google_sheet,
    "read_google_sheet": read_google_sheet,
    "write_google_sheet": write_google_sheet,
    "create_google_sheet": create_google_sheet,
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

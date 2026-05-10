"""Tool registry — JSON schemas + dispatcher + file-collection."""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from loguru import logger

from src.tools.google_sheets_tool import (
    create_google_sheet,
    find_google_sheet,
    read_google_sheet,
    write_google_sheet,
)
from src.tools.skills_tools import (
    generate_chart,
    generate_docx,
    generate_pdf,
    generate_pptx,
)
from src.tools.web_fetch import web_fetch

# --- File side-channel ---------------------------------------------------
# Tools that produce files write their file_path here; the brain loop reads
# this list at the end of a turn and hands it to the Telegram handler.
_files_for_turn: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "files_for_turn", default=None
)


def reset_file_collector() -> list[dict[str, Any]]:
    """Initialise an empty list for the current turn. Returns the list."""
    files: list[dict[str, Any]] = []
    _files_for_turn.set(files)
    return files


def collect_files() -> list[dict[str, Any]]:
    files = _files_for_turn.get()
    return files if files is not None else []


# -------------------------------------------------------------------------

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
                "properties": {"url": {"type": "string"}},
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
                "ALWAYS call this first to get the spreadsheet_id before reading or writing."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_google_sheet",
            "description": (
                "Read a range from a spreadsheet. Output is TSV, capped at 100 rows."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {"type": "string", "description": "A1 notation, default A1:Z200."},
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
                "Write a 2D block of values into a spreadsheet range. "
                "Only works on sheets where Vladimir is editor/owner."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {"type": "string"},
                    "values_csv": {
                        "type": "string",
                        "description": "Rows by '\\n', cells by TAB or comma.",
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
            "description": "Create a new spreadsheet in Vladimir's Drive (he becomes owner).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "headers_csv": {"type": "string"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_pptx",
            "description": (
                "Build a clean .pptx presentation. Output goes to the user as a file in Telegram. "
                "`slides_json` is a JSON array. Each slide object: "
                '{"title": "...", "bullets": ["...", "..."]} or {"title": "...", "body": "..."}.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title slide heading."},
                    "subtitle": {
                        "type": "string",
                        "description": "Optional subtitle on title slide.",
                    },
                    "slides_json": {
                        "type": "string",
                        "description": "JSON array of slide objects (see description).",
                    },
                },
                "required": ["title", "slides_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_docx",
            "description": (
                "Build a clean .docx file. Output goes to the user as a file in Telegram. "
                "`sections_json` is a JSON array of sections, each: "
                '{"heading": "...", "paragraphs": ["...", ...], "bullets": ["...", ...]}.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "sections_json": {"type": "string"},
                },
                "required": ["title", "sections_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_pdf",
            "description": (
                "Build a clean PDF. `sections_json` like generate_docx, plus optional "
                '"table": {"headers": [...], "rows": [[...], ...]} per section.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "sections_json": {"type": "string"},
                },
                "required": ["title", "sections_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_chart",
            "description": (
                "Render a single chart as PNG. Output goes to the user as an image in Telegram."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "enum": ["bar", "line", "pie"]},
                    "title": {"type": "string"},
                    "labels_csv": {
                        "type": "string",
                        "description": "Comma-separated labels for the X axis (or pie wedges).",
                    },
                    "values_csv": {
                        "type": "string",
                        "description": "Comma-separated numeric values, same length as labels.",
                    },
                    "y_label": {"type": "string"},
                },
                "required": ["chart_type", "title", "labels_csv", "values_csv"],
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
    "generate_pptx": generate_pptx,
    "generate_docx": generate_docx,
    "generate_pdf": generate_pdf,
    "generate_chart": generate_chart,
}


_FILE_PRODUCING_TOOLS = {
    "generate_pptx",
    "generate_docx",
    "generate_pdf",
    "generate_chart",
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
        result = await fn(**args)
    except Exception as e:
        logger.exception("tool {} failed", name)
        return f"error executing {name}: {type(e).__name__}: {e}"

    # Side-channel: if a file-producing tool succeeded, push the file to the
    # current turn's collector so the handler can ship it to Telegram.
    if name in _FILE_PRODUCING_TOOLS:
        try:
            payload = json.loads(result)
            if isinstance(payload, dict) and payload.get("ok") and payload.get("file_path"):
                collected = _files_for_turn.get()
                if collected is not None:
                    collected.append(
                        {
                            "path": payload["file_path"],
                            "name": payload.get("file_name"),
                            "kind": payload.get("kind"),
                        }
                    )
        except Exception:
            pass

    return result

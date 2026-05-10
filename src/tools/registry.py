"""Tool registry — JSON schemas + dispatcher + file-collection."""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from loguru import logger

from src.tools.google_sheets_tool import (
    create_google_sheet,
    find_google_sheet,
    list_google_sheet_tabs,
    read_google_sheet,
    write_google_sheet,
)
from src.tools.memory_tools import (
    clear_focus,
    forget,
    recall,
    remember,
    set_active_sheet,
    set_active_spreadsheet,
    set_focus,
)
from src.tools.skills_tools import (
    generate_chart,
    generate_docx,
    generate_pdf,
    generate_pptx,
)
from src.tools.web_fetch import web_fetch

# --- File side-channel ---------------------------------------------------
_files_for_turn: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "files_for_turn", default=None
)


def reset_file_collector() -> list[dict[str, Any]]:
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
            "description": "Fetch the readable text content of a public URL.",
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
                "Returns up to 8 matches. Pass empty string to list recent sheets."
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
            "name": "list_google_sheet_tabs",
            "description": (
                "List all sheets/tabs inside a spreadsheet (titles, indexes, sizes). "
                "ALWAYS call this right after set_active_spreadsheet before read_google_sheet, "
                "so you know which tab to read instead of guessing."
            ),
            "parameters": {
                "type": "object",
                "properties": {"spreadsheet_id": {"type": "string"}},
                "required": ["spreadsheet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_google_sheet",
            "description": (
                "Read a range from a spreadsheet (TSV, capped at 100 rows). "
                "If the spreadsheet has multiple sheets, ALWAYS prefix the range with "
                "the sheet name in single quotes: \"'Заказы 2026'!A1:Z200\". "
                "Without the sheet prefix, Google reads the first tab — which may not "
                "be the one you need."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {
                        "type": "string",
                        "description": (
                            "A1 with sheet prefix, e.g. \"'Заказы 2026'!A1:Z200\". "
                            "Default: 'A1:Z200' on the first tab."
                        ),
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
            "description": "Write a 2D block of values into a spreadsheet range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {"type": "string"},
                    "values_csv": {"type": "string"},
                },
                "required": ["spreadsheet_id", "range", "values_csv"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_google_sheet",
            "description": "Create a new spreadsheet in Vladimir's Drive.",
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
    # ── Session state / memory ──────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "set_active_spreadsheet",
            "description": (
                "Pin a spreadsheet as the current focus. Call this right after "
                "find_google_sheet when you've identified the right table — then "
                "you don't have to keep asking which one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["spreadsheet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_active_sheet",
            "description": "Pin which sheet/tab inside the active spreadsheet is in focus.",
            "parameters": {
                "type": "object",
                "properties": {"sheet_name": {"type": "string"}},
                "required": ["sheet_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_focus",
            "description": "Pin free-form note about the current focus of the conversation.",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_focus",
            "description": "Drop all session focus pins (active spreadsheet/sheet/topic).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": (
                "Pin a fact in long-term memory. Call when the user shares something "
                "durable — names of partners, recurring rules, project meanings. "
                "Don't pin transient stuff like 'today I'm tired'."
            ),
            "parameters": {
                "type": "object",
                "properties": {"fact": {"type": "string"}},
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": (
                "Search Vladimir's pinned facts. Pass a keyword/substring or "
                "omit `query` to get 10 most recent."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget",
            "description": "Delete pinned facts that match the query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    # ── Generators ─────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "generate_pptx",
            "description": (
                "Build a clean .pptx presentation. Output goes to the user as a Telegram file. "
                "`slides_json`: JSON array of {title, bullets[]} or {title, body}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "slides_json": {"type": "string"},
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
                "Build a clean .docx file. `sections_json`: JSON array of "
                "{heading, paragraphs[], bullets[]}."
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
            "description": "Build a clean PDF (sections like generate_docx + optional `table`).",
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
            "description": "Render a single PNG chart (bar/line/pie).",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "enum": ["bar", "line", "pie"]},
                    "title": {"type": "string"},
                    "labels_csv": {"type": "string"},
                    "values_csv": {"type": "string"},
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
    "list_google_sheet_tabs": list_google_sheet_tabs,
    "read_google_sheet": read_google_sheet,
    "write_google_sheet": write_google_sheet,
    "create_google_sheet": create_google_sheet,
    "set_active_spreadsheet": set_active_spreadsheet,
    "set_active_sheet": set_active_sheet,
    "set_focus": set_focus,
    "clear_focus": clear_focus,
    "remember": remember,
    "recall": recall,
    "forget": forget,
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

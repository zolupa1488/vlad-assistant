"""Tool registry — JSON schemas + dispatcher + file-collection."""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from loguru import logger

from src.tools.figma_tool import (
    figma_export_image,
    figma_get_comments,
    figma_get_file,
)
from src.tools.google_sheets_tool import (
    create_google_sheet,
    find_google_sheet,
    list_google_sheet_tabs,
    read_google_sheet,
    write_google_sheet,
)
from src.tools.image_gen import generate_image
from src.tools.mac_bridge_tool import mac_bridge_run
from src.tools.memory_tools import (
    clear_focus,
    forget,
    recall,
    remember,
    set_active_sheet,
    set_active_spreadsheet,
    set_focus,
)
from src.tools.model_tools import escalate_to_sonnet, whoami_model
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
            "name": "mac_bridge_run",
            "description": (
                "Delegate a task to Vladimir's Mac, which runs Claude Code with MCP "
                "servers (Figma, Canva, file-system, etc). Use for: working with "
                "Figma designs, Canva mockups, building static websites, anything that "
                "needs Vladimir's local environment. The task should be a clear, "
                "self-contained instruction in plain Russian or English. The Mac must "
                "be awake — if asleep or tunnel down, returns an error."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Self-contained instruction for Claude Code on the Mac.",
                    },
                },
                "required": ["task"],
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
    # ── Image generation (nano-banana via OpenRouter) ──────────────
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": (
                "Generate a PNG image from a text prompt using Gemini 2.5 Flash "
                "Image (nano-banana) via OpenRouter. Prompt in English works best. "
                "The image is shipped to Telegram as a photo automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "What to generate, ideally in English.",
                    }
                },
                "required": ["prompt"],
            },
        },
    },
    # ── Figma read + render via REST API ──────────────────────────
    {
        "type": "function",
        "function": {
            "name": "figma_get_file",
            "description": (
                "Read top-level structure of a Figma file: pages and their "
                "frames with node_ids. Pass a full Figma URL or just the file_key. "
                "Use the node_ids from this output with figma_export_image."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url_or_key": {
                        "type": "string",
                        "description": "Figma URL or bare file_key",
                    }
                },
                "required": ["url_or_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "figma_export_image",
            "description": (
                "Export a Figma node (frame/component/group) as image and ship "
                "it to Telegram. Get the node_id from figma_get_file first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url_or_key": {"type": "string"},
                    "node_id": {"type": "string"},
                    "format": {
                        "type": "string",
                        "enum": ["png", "jpg", "svg", "pdf"],
                    },
                    "scale": {
                        "type": "number",
                        "description": "Render scale, default 2.0 for retina-quality PNG.",
                    },
                },
                "required": ["url_or_key", "node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "figma_get_comments",
            "description": "Read comments left on a Figma file.",
            "parameters": {
                "type": "object",
                "properties": {"url_or_key": {"type": "string"}},
                "required": ["url_or_key"],
            },
        },
    },
    # ── Model-tier controls ───────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "escalate_to_sonnet",
            "description": (
                "ESCALATE TO SONNET 4. Call this when you (running as Haiku 4.5) "
                "feel the task is too complex — long reasoning, nuanced creative "
                "writing, multi-step analysis. The next hop will run on Sonnet 4 "
                "with the same context. Don't overuse — only when you actually "
                "feel stuck or about to produce mediocre output. Pass a brief "
                "reason."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief reason in Russian — why this needs Sonnet.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "whoami_model",
            "description": (
                "Return the LLM tier currently powering this turn. Call when the "
                "user asks 'какая модель' / 'на чём ты сейчас отвечаешь'."
            ),
            "parameters": {"type": "object", "properties": {}},
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
    "generate_image": generate_image,
    "figma_get_file": figma_get_file,
    "figma_export_image": figma_export_image,
    "figma_get_comments": figma_get_comments,
    "mac_bridge_run": mac_bridge_run,
    "escalate_to_sonnet": escalate_to_sonnet,
    "whoami_model": whoami_model,
}


_FILE_PRODUCING_TOOLS = {
    "generate_pptx",
    "generate_docx",
    "generate_pdf",
    "generate_chart",
    "generate_image",
    "figma_export_image",
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

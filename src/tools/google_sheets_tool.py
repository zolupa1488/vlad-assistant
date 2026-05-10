"""Claude-side tools for Google Sheets / Drive."""

from __future__ import annotations

import asyncio
import json

from src.integrations import google_sheets as gs


async def find_google_sheet(query: str) -> str:
    """Search Drive for spreadsheets by name (substring, case-insensitive)."""
    files = await asyncio.to_thread(gs.find_sheets, query, 8)
    if not files:
        return f"Ни одной таблицы с '{query}' в названии не нашёл."
    short = [
        {
            "id": f["id"],
            "name": f["name"],
            "url": f.get("webViewLink"),
            "modified": f.get("modifiedTime"),
            "owner": (f.get("owners") or [{}])[0].get("emailAddress"),
        }
        for f in files
    ]
    return json.dumps(short, ensure_ascii=False, indent=2)


async def list_google_sheet_tabs(spreadsheet_id: str) -> str:
    """List all sheets/tabs inside a spreadsheet."""
    tabs = await asyncio.to_thread(gs.list_tabs, spreadsheet_id)
    if not tabs:
        return "(в таблице нет листов)"
    return json.dumps(tabs, ensure_ascii=False, indent=2)


async def read_google_sheet(spreadsheet_id: str, range: str = "A1:Z500") -> str:
    """Read a range from a spreadsheet. Returns TSV-like text capped at 500 rows."""
    rows = await asyncio.to_thread(gs.read_range, spreadsheet_id, range)
    if not rows:
        return "(empty)"
    truncated = False
    if len(rows) > 500:
        rows = rows[:500]
        truncated = True
    out = "\n".join("\t".join(str(c) for c in r) for r in rows)
    if truncated:
        out += "\n…(truncated to first 500 rows)"
    return out


async def write_google_sheet(spreadsheet_id: str, range: str, values_csv: str) -> str:
    """Write a 2D block. `values_csv` — rows separated by '\\n', cells by '\\t' (or ',')."""
    rows: list[list] = []
    for line in values_csv.splitlines():
        if "\t" in line:
            rows.append(line.split("\t"))
        else:
            rows.append([c.strip() for c in line.split(",")])
    n = await asyncio.to_thread(gs.write_range, spreadsheet_id, range, rows)
    return f"updated {n} cells"


async def create_google_sheet(title: str, headers_csv: str | None = None) -> str:
    """Create a new spreadsheet in the user's Drive. Optionally write headers to row 1."""
    headers = [c.strip() for c in headers_csv.split(",")] if headers_csv else None
    info = await asyncio.to_thread(gs.create_spreadsheet, title, headers)
    return json.dumps(info, ensure_ascii=False)

"""Thin wrapper over Drive (search) + Sheets (read/write/create)."""

from __future__ import annotations

from googleapiclient.discovery import build

from src.integrations.google_oauth import get_credentials


def _drive():
    return build("drive", "v3", credentials=get_credentials(), cache_discovery=False)


def _sheets():
    return build("sheets", "v4", credentials=get_credentials(), cache_discovery=False)


def find_sheets(query: str, limit: int = 10) -> list[dict]:
    """Search Drive for spreadsheets whose name contains `query`."""
    drive = _drive()
    safe_q = query.replace("'", "\\'")
    q = (
        "mimeType = 'application/vnd.google-apps.spreadsheet' "
        f"and name contains '{safe_q}' and trashed = false"
    )
    res = (
        drive.files()
        .list(
            q=q,
            pageSize=limit,
            fields="files(id, name, webViewLink, modifiedTime, owners(emailAddress))",
            orderBy="modifiedTime desc",
        )
        .execute()
    )
    return res.get("files", [])


def list_tabs(spreadsheet_id: str) -> list[dict]:
    """Return [{title, sheet_id, index, rows, cols}, ...] for every tab in the spreadsheet."""
    sheets = _sheets()
    res = (
        sheets.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title,index,gridProperties))",
        )
        .execute()
    )
    out = []
    for s in res.get("sheets", []):
        p = s.get("properties", {})
        gp = p.get("gridProperties", {})
        out.append(
            {
                "title": p.get("title"),
                "sheet_id": p.get("sheetId"),
                "index": p.get("index"),
                "rows": gp.get("rowCount"),
                "cols": gp.get("columnCount"),
            }
        )
    return out


def read_range(spreadsheet_id: str, range_a1: str) -> list[list]:
    sheets = _sheets()
    res = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_a1, majorDimension="ROWS")
        .execute()
    )
    return res.get("values", [])


def write_range(spreadsheet_id: str, range_a1: str, values: list[list]) -> int:
    sheets = _sheets()
    body = {"values": values}
    res = (
        sheets.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
            valueInputOption="USER_ENTERED",
            body=body,
        )
        .execute()
    )
    return int(res.get("updatedCells", 0))


def create_spreadsheet(title: str, headers: list[str] | None = None) -> dict:
    sheets = _sheets()
    res = sheets.spreadsheets().create(body={"properties": {"title": title}}).execute()
    info = {
        "id": res["spreadsheetId"],
        "url": res.get("spreadsheetUrl"),
        "title": title,
    }
    if headers:
        write_range(info["id"], "A1", [headers])
    return info

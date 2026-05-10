"""Claude-side tool wrappers for the local skills (pptx/docx/pdf/chart)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from src.skills.chart_skill import generate_chart as _chart
from src.skills.docx_skill import generate_docx as _docx
from src.skills.pdf_skill import generate_pdf as _pdf
from src.skills.pptx_skill import generate_pptx as _pptx


def _ok(path: str, kind: str) -> str:
    return json.dumps(
        {
            "ok": True,
            "kind": kind,
            "file_path": path,
            "file_name": os.path.basename(path),
            "size_bytes": os.path.getsize(path),
        },
        ensure_ascii=False,
    )


async def generate_pptx(title: str, slides_json: str, subtitle: str | None = None) -> str:
    """Run python-pptx in a thread (blocking lib)."""
    try:
        slides: list[dict[str, Any]] = json.loads(slides_json)
        assert isinstance(slides, list)
    except Exception as e:
        return f"slides_json must be a JSON array of slide objects: {e}"
    path = await asyncio.to_thread(_pptx, title, subtitle, slides)
    return _ok(path, "pptx")


async def generate_docx(title: str, sections_json: str) -> str:
    try:
        sections: list[dict[str, Any]] = json.loads(sections_json)
        assert isinstance(sections, list)
    except Exception as e:
        return f"sections_json must be a JSON array of section objects: {e}"
    path = await asyncio.to_thread(_docx, title, sections)
    return _ok(path, "docx")


async def generate_pdf(title: str, sections_json: str) -> str:
    try:
        sections: list[dict[str, Any]] = json.loads(sections_json)
        assert isinstance(sections, list)
    except Exception as e:
        return f"sections_json must be a JSON array of section objects: {e}"
    path = await asyncio.to_thread(_pdf, title, sections)
    return _ok(path, "pdf")


async def generate_chart(
    chart_type: str,
    title: str,
    labels_csv: str,
    values_csv: str,
    y_label: str | None = None,
) -> str:
    labels = [s.strip() for s in labels_csv.split(",") if s.strip()]
    try:
        values = [float(s.strip()) for s in values_csv.split(",") if s.strip()]
    except ValueError as e:
        return f"values_csv must be comma-separated numbers: {e}"
    if len(labels) != len(values):
        return f"labels ({len(labels)}) and values ({len(values)}) length mismatch"
    path = await asyncio.to_thread(_chart, chart_type, title, labels, values, y_label)
    return _ok(path, "image")

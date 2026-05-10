"""Generate a PDF report from structured outline."""

from __future__ import annotations

import os
import uuid

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT_DIR = os.environ.get("FILES_OUTPUT_DIR", "/app/data/files")


def generate_pdf(title: str, sections: list[dict]) -> str:
    """Build a clean PDF and return the absolute path.

    `sections`: list[dict] with optional keys: heading, paragraphs, bullets, table.
    `table`: {"headers": [...], "rows": [[...], ...]}
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fname = f"doc-{uuid.uuid4().hex[:8]}.pdf"
    path = os.path.join(OUTPUT_DIR, fname)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "T", parent=styles["Heading1"], fontSize=22, leading=28,
        textColor=HexColor("#1f1f1f"), spaceAfter=14,
    )
    h_style = ParagraphStyle(
        "H", parent=styles["Heading2"], fontSize=14, leading=18,
        textColor=HexColor("#1f1f1f"), spaceBefore=10, spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "B", parent=styles["BodyText"], fontSize=11, leading=15,
        textColor=HexColor("#1f1f1f"), spaceAfter=6,
    )

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    flow: list = [Paragraph(title, title_style)]
    for s in sections:
        heading = s.get("heading")
        if heading:
            flow.append(Paragraph(heading, h_style))
        for para in s.get("paragraphs") or []:
            flow.append(Paragraph(para, body_style))
        for bullet in s.get("bullets") or []:
            flow.append(Paragraph("•&nbsp;&nbsp;" + bullet, body_style))
        table = s.get("table")
        if table and table.get("headers") and table.get("rows"):
            data = [table["headers"]] + table["rows"]
            t = Table(data, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#eeeeee")),
                ("TEXTCOLOR", (0, 0), (-1, -1), black),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#fafafa")]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, black),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]))
            flow.append(t)
        flow.append(Spacer(1, 8))

    doc.build(flow)
    return path

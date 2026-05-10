"""Generate a PNG chart from structured data via matplotlib."""

from __future__ import annotations

import os
import uuid

import matplotlib

matplotlib.use("Agg")  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

OUTPUT_DIR = os.environ.get("FILES_OUTPUT_DIR", "/app/data/files")


def generate_chart(
    chart_type: str,
    title: str,
    labels: list[str],
    values: list[float],
    y_label: str | None = None,
) -> str:
    """Build a single PNG chart.

    `chart_type`: "bar" | "line" | "pie".
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fname = f"chart-{uuid.uuid4().hex[:8]}.png"
    path = os.path.join(OUTPUT_DIR, fname)

    fig, ax = plt.subplots(figsize=(10, 6), dpi=140)
    fig.patch.set_facecolor("#f8f8f6")
    ax.set_facecolor("#f8f8f6")

    color = "#cc785c"
    if chart_type == "bar":
        ax.bar(labels, values, color=color, edgecolor="none")
    elif chart_type == "line":
        ax.plot(labels, values, color=color, linewidth=2.4, marker="o")
    elif chart_type == "pie":
        ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90,
               wedgeprops=dict(edgecolor="white", linewidth=2))
        ax.set_aspect("equal")
    else:
        raise ValueError(f"unknown chart_type: {chart_type}")

    ax.set_title(title, fontsize=16, fontweight="bold", color="#1f1f1f", pad=14)
    if chart_type != "pie":
        ax.tick_params(colors="#1f1f1f")
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("bottom", "left"):
            ax.spines[spine].set_color("#888888")
        if y_label:
            ax.set_ylabel(y_label, color="#1f1f1f")
        if chart_type == "bar":
            for tick in ax.get_xticklabels():
                tick.set_rotation(20)
                tick.set_ha("right")

    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight", facecolor="#f8f8f6")
    plt.close(fig)
    return path

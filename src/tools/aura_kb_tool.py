"""AURA business knowledge base tool.

Loads the AURA training pack (src/data/aura_kb.json) and lets Friman pull
specific sections on demand. Saves system-prompt tokens — the full KB is ~16KB
which is too heavy to bake into every turn, but it's instantly available when
the user asks something business-specific.

Sections available — top-level keys of the JSON:
    brand, audiences, products, visual_success_formula, presentation_rules,
    what_hits, series_sales, pricing, cost_structure, financials,
    analytics_heuristics, marketing, messaging_rules, prompting_stack, ops,
    expansion, glossary, meta

Special:
    "all" — full dump (heavy, only when really needed)
    "list" — just the list of available sections
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

_KB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "aura_kb.json",
)


@lru_cache(maxsize=1)
def _load_kb() -> dict:
    """Cached single load of the KB."""
    with open(_KB_PATH, encoding="utf-8") as f:
        return json.load(f)


async def aura_kb(section: str = "list") -> str:
    """Return a section of the AURA business knowledge base.

    section: one of the top-level keys (brand, products, pricing, financials,
             visual_success_formula, what_hits, marketing, messaging_rules,
             ops, expansion, glossary, etc.), or "all" for full dump,
             or "list" to see what sections exist (default).
    """
    try:
        kb = _load_kb()
    except FileNotFoundError:
        return json.dumps(
            {"error": "aura_kb.json не найдена в src/data/"},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {"error": f"не смог распарсить aura_kb.json: {type(e).__name__}: {e}"},
            ensure_ascii=False,
        )

    section = (section or "list").strip().lower()

    if section == "list":
        keys = list(kb.keys())
        return json.dumps(
            {
                "available_sections": keys,
                "hint": (
                    "вызывай aura_kb с одной из секций. 'all' даст всё сразу — "
                    "тяжёлое, использовать только для широких задач."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )

    if section == "all":
        return json.dumps(kb, ensure_ascii=False, indent=2)

    if section in kb:
        return json.dumps({section: kb[section]}, ensure_ascii=False, indent=2)

    # Try fuzzy / partial match
    matches = [k for k in kb.keys() if section in k.lower() or k.lower() in section]
    if len(matches) == 1:
        k = matches[0]
        return json.dumps({k: kb[k]}, ensure_ascii=False, indent=2)
    if len(matches) > 1:
        return json.dumps(
            {
                "error": f"неоднозначный section '{section}'",
                "did_you_mean": matches,
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "error": f"секция '{section}' не найдена",
            "available_sections": list(kb.keys()),
        },
        ensure_ascii=False,
    )

"""Tools the LLM uses to control which model tier is active.

- `escalate_to_sonnet(reason)` — Haiku calls this when it judges itself
  not strong enough for the task at hand. The actual tier switch is
  handled by the tool-use loop after this call returns.
- `whoami_model()` — return the current tier so the LLM can answer
  "какая у тебя модель?" naturally without making things up.

Both rely on a ContextVar that the loop fills in before each turn.
"""

from __future__ import annotations

import json
from contextvars import ContextVar

# Filled in by tool_use_loop.respond() at the start of each turn.
_current_tier: ContextVar[str] = ContextVar("current_tier", default="haiku")
_escalation_signal: ContextVar[dict | None] = ContextVar(
    "escalation_signal", default=None
)


def set_current_tier(tier: str) -> None:
    _current_tier.set(tier)


def get_current_tier() -> str:
    return _current_tier.get()


def reset_escalation_signal() -> None:
    _escalation_signal.set(None)


def consume_escalation_signal() -> dict | None:
    sig = _escalation_signal.get()
    _escalation_signal.set(None)
    return sig


async def escalate_to_sonnet(reason: str = "") -> str:
    """Marker tool. The tool-use loop reads the escalation signal after
    this call and switches the tier for the next hop."""
    _escalation_signal.set({"target": "sonnet", "reason": reason or "complex task"})
    return json.dumps(
        {
            "ok": True,
            "message": (
                "эскалация принята. следующий хоп пойдёт на Sonnet 4. "
                "продолжай задачу как есть, контекст сохранён."
            ),
        },
        ensure_ascii=False,
    )


async def whoami_model() -> str:
    tier = _current_tier.get()
    if tier == "sonnet":
        label = "Claude Sonnet 4"
    else:
        label = "Claude Haiku 4.5"
    return json.dumps({"tier": tier, "human_label": label}, ensure_ascii=False)

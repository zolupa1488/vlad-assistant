"""Claude-side tool that delegates a task to Vladimir's Mac (Claude Code + MCPs)."""

from __future__ import annotations

import json

from src.integrations import mac_bridge


async def mac_bridge_run(task: str) -> str:
    """Send `task` to the local Mac. Use for things that require Vladimir's
    local Claude Code with its MCP servers (Figma, Canva, file system on Mac, etc.).

    The Mac must be awake; if it's asleep or the tunnel is down, this returns
    an error string."""
    try:
        result = await mac_bridge.run_on_mac(task)
    except Exception as e:
        return (
            f"Mac недоступен: {type(e).__name__}: {e}. "
            "Возможно ноут спит или туннель упал."
        )

    # Compact result for the LLM — full stdout + short stderr if any.
    out = {
        "ok": result.get("ok", False),
        "stdout": result.get("stdout", "")[:6000],
        "stderr": result.get("stderr", "")[:1000],
        "exit_code": result.get("exit_code"),
    }
    return json.dumps(out, ensure_ascii=False)

"""Key presses for the MCP tools: the library's key table
(:mod:`tellurium.browser.keys`), with an unknown key as a ``ToolError`` the agent
reads, never a silently sent event.
"""

from __future__ import annotations

from typing import Any

from tellurium.browser import keys
from tellurium.mcp.results import ToolError


def parse(combo: str) -> keys.Key:
    """``"Control+a"`` -> (key, modifiers, virtual key code, text)."""
    try:
        return keys.parse(combo)
    except ValueError as exc:
        raise ToolError(str(exc)) from None


async def press(tab: Any, combo: str, *, human: bool = True) -> None:
    """Press and release *combo* in the focused element of *tab*."""
    parse(combo)
    await tab.keyboard_press(combo, human=human)

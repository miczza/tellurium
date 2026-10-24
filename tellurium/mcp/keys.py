"""Key presses the page really acts on: ``Enter`` submits, arrows move a
``<select>``. Chrome needs the virtual key code (and the text of a printable
key) to act; a key it would not know is refused, never silently sent.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from tellurium.mcp.results import ToolError

# name -> (Windows virtual key code, text it types)
_NAMED: dict[str, tuple[int, str]] = {
    "Enter": (13, "\r"),
    "Tab": (9, ""),
    "Escape": (27, ""),
    "Backspace": (8, ""),
    "Delete": (46, ""),
    "Insert": (45, ""),
    "Space": (32, " "),
    "ArrowUp": (38, ""),
    "ArrowDown": (40, ""),
    "ArrowLeft": (37, ""),
    "ArrowRight": (39, ""),
    "Home": (36, ""),
    "End": (35, ""),
    "PageUp": (33, ""),
    "PageDown": (34, ""),
    **{f"F{n}": (111 + n, "") for n in range(1, 13)},
}
# CDP modifier bits
_MODIFIERS = {"alt": 1, "control": 2, "ctrl": 2, "meta": 4, "cmd": 4, "command": 4, "shift": 8}
_PUNCTUATION = {";": 186, "=": 187, ",": 188, "-": 189, ".": 190, "/": 191, "`": 192}
_PUNCTUATION |= {"[": 219, "\\": 220, "]": 221, "'": 222, " ": 32}


def parse(combo: str) -> tuple[str, int, int, str]:
    """``"Control+a"`` -> (key, modifiers, virtual key code, text)."""
    *mods, key = combo.split("+") if combo != "+" else ["+"]
    bits = 0
    for mod in mods:
        if mod.lower() not in _MODIFIERS:
            raise ToolError(f"Unknown modifier {mod!r} in {combo!r}: use Control, Alt, Shift, Meta")
        bits |= _MODIFIERS[mod.lower()]
    if key in _NAMED:
        code, text = _NAMED[key]
        return (" " if key == "Space" else key), bits, code, text
    if len(key) == 1 and key.isprintable():
        if key.isalnum() and key.isascii():
            code = ord(key.upper())
        else:
            code = _PUNCTUATION.get(key, 0)
        return key, bits, code, key
    names = ", ".join(sorted(_NAMED))
    raise ToolError(f"Unknown key {key!r}: use one character or one of {names}")


async def press(tab: Any, combo: str, *, human: bool = True) -> None:
    """Press and release *combo* in the focused element of *tab*."""
    key, bits, code, text = parse(combo)
    if bits & (2 | 4):  # Control/Meta shortcuts type nothing
        text = ""
    base = {"key": key, "modifiers": bits, "windowsVirtualKeyCode": code}
    base["nativeVirtualKeyCode"] = code
    await tab.send_cdp("Input.dispatchKeyEvent", {**base, "type": "rawKeyDown"})
    if text:
        await tab.send_cdp("Input.dispatchKeyEvent", {**base, "type": "char", "text": text})
    if human:
        await asyncio.sleep(random.uniform(0.04, 0.11))  # a finger's dwell on the key
    await tab.send_cdp("Input.dispatchKeyEvent", {**base, "type": "keyUp"})

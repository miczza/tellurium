"""Key presses the page really acts on: ``Enter`` submits, arrows move a
``<select>``, ``Control+a`` selects all. Chrome needs the Windows virtual key
code (and the text of a printable key) to act; a key it would not know is
refused with ``ValueError`` before any event is sent, never silently dropped.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple

# name -> (Windows virtual key code, text it types)
NAMED: dict[str, tuple[int, str]] = {
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
ALT, CONTROL, META, SHIFT = 1, 2, 4, 8
_MODIFIERS = {
    "alt": ALT,
    "control": CONTROL,
    "ctrl": CONTROL,
    "meta": META,
    "cmd": META,
    "command": META,
    "shift": SHIFT,
}
_PUNCTUATION = {";": 186, "=": 187, ",": 188, "-": 189, ".": 190, "/": 191, "`": 192}
_PUNCTUATION |= {"[": 219, "\\": 220, "]": 221, "'": 222, " ": 32}

Send = Callable[[str, dict[str, Any]], Awaitable[Any]]


class Key(NamedTuple):
    """One parsed key combo."""

    key: str  # the DOM ``key`` value
    modifiers: int  # CDP modifier bits
    code: int  # Windows virtual key code (0 when Chrome has none for it)
    text: str  # what the key types, before modifiers ("" for none)


def parse(combo: str) -> Key:
    """``"Control+a"`` -> ``Key("a", 2, 65, "a")``; ``ValueError`` for an unknown
    key or modifier."""
    *mods, key = combo.split("+") if combo != "+" else ["+"]
    bits = 0
    for mod in mods:
        if mod.lower() not in _MODIFIERS:
            raise ValueError(
                f"Unknown modifier {mod!r} in {combo!r}: use Control, Alt, Shift, Meta"
            )
        bits |= _MODIFIERS[mod.lower()]
    if key in NAMED:
        code, text = NAMED[key]
        return Key(" " if key == "Space" else key, bits, code, text)
    if len(key) == 1 and key.isprintable():
        if key.isalnum() and key.isascii():
            code = ord(key.upper())
        else:
            code = _PUNCTUATION.get(key, 0)
        return Key(key, bits, code, key)
    names = ", ".join(sorted(NAMED))
    raise ValueError(f"Unknown key {key!r}: use one character or one of {names}")


def event(key: Key, kind: str) -> dict[str, Any]:
    """The ``Input.dispatchKeyEvent`` parameters of one *kind* of event for *key*
    (no text: only a ``char`` event carries it)."""
    code = key.code
    return {
        "type": kind,
        "key": key.key,
        "modifiers": key.modifiers,
        "windowsVirtualKeyCode": code,
        "nativeVirtualKeyCode": code,
    }


async def press(send: Send, combo: str, *, human: bool = False) -> None:
    """Press and release *combo* through *send* (``send(method, params)``):
    ``rawKeyDown``, ``char`` when the key types text (never with Control or
    Meta), ``keyUp``. *human* holds the key 40-110 ms, as a finger does."""
    key = parse(combo)
    text = "" if key.modifiers & (CONTROL | META) else key.text
    await send("Input.dispatchKeyEvent", event(key, "rawKeyDown"))
    if text:
        await send("Input.dispatchKeyEvent", {**event(key, "char"), "text": text})
    if human:
        await asyncio.sleep(random.uniform(0.04, 0.11))
    await send("Input.dispatchKeyEvent", event(key, "keyUp"))


def typing_event(char: str, kind: str) -> dict[str, Any] | None:
    """The ``Input.dispatchKeyEvent`` parameters of one event (``rawKeyDown``, ``char``,
    ``keyUp``) of the human typing path for *char*; ``None`` for an event it skips."""
    if len(char) > 1:  # a named key (the typo path's Backspace): never any text
        if kind == "char":
            return None
        return {**event(parse(char), "keyDown" if kind == "rawKeyDown" else "keyUp"), "code": char}
    if not char.isalpha():  # the text rides on keyDown, as on the plain path
        return dict(zip(("rawKeyDown", "keyUp"), plain_events(char), strict=True)).get(kind)
    if kind == "char":
        return {"type": "char", "text": char, "key": char}
    if kind not in ("rawKeyDown", "keyUp"):
        return None
    code = ord(char.upper()) if char.isascii() else 0
    return {"type": kind, "key": char, "code": f"Key{char.upper()}", "windowsVirtualKeyCode": code}


def plain_events(char: str) -> list[dict[str, Any]]:
    """The events that type *char* at once: ``keyDown`` with its text, ``keyUp``."""
    return [{"type": "keyDown", "key": char, "text": char}, {"type": "keyUp", "key": char}]

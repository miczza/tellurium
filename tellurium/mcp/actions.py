"""Tools that act on a snapshot ref: click, fill, press, select-option, check,
hover, scroll, download. Input is human-like unless ``human: false``.

An action returns ``{ok, url, title, navigated}``, not a new snapshot: the
agent asks for one when it needs it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from tellurium.browser.tab import Tab
from tellurium.mcp import page_state
from tellurium.mcp.pages import ref_element, state_data
from tellurium.mcp.results import Reply, ToolError
from tellurium.mcp.tool import Tool, param

DOWNLOAD_DEFAULT = 60
DOWNLOAD_MAX = 600
SCROLL_DEFAULT = 600

# Select by value, else by the visible label: the snapshot shows labels.
_SELECT = """function() {
  const wanted = __WANTED__;
  const options = Array.from(this.options || []);
  const hit = options.find(o => o.value === wanted)
    || options.find(o => o.label.trim() === wanted.trim());
  if (!hit) return null;
  this.value = hit.value;
  this.dispatchEvent(new Event('input', {bubbles: true}));
  this.dispatchEvent(new Event('change', {bubbles: true}));
  return hit.value;
}"""


async def _act(
    args: dict[str, Any], tab: Tab, what: str, action: Callable[[], Awaitable[Any]]
) -> Reply:
    before = await page_state.read_or_none(tab)
    await action()
    state, navigated = await page_state.after_action(tab, before)
    data = state_data(args["targetId"], state, ok=True, navigated=navigated)
    where = f"navigated to {state.url}" if navigated else f"on {state.url}"
    return Reply(f"{what}; {where} ({state.title})", data)


def _human(args: dict[str, Any]) -> bool:
    return args.get("human", True)


async def _click(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    element = await ref_element(tab, args["ref"])
    return await _act(
        args, tab, f"clicked {args['ref']}", lambda: element.click(human=_human(args))
    )


async def _fill(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    element = await ref_element(tab, args["ref"])

    async def fill() -> None:
        await element.type(args["text"], human=_human(args), clear=True)
        if args.get("submit"):
            await tab.keyboard_press("Enter")

    return await _act(args, tab, f"filled {args['ref']}", fill)


async def _press(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])

    async def press() -> None:
        if "ref" in args:
            await (await ref_element(tab, args["ref"])).focus()
        await tab.keyboard_press(args["key"])

    return await _act(args, tab, f"pressed {args['key']}", press)


async def _select_option(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    element = await ref_element(tab, args["ref"])

    async def select() -> None:
        chosen = await element.apply(_SELECT.replace("__WANTED__", json.dumps(args["value"])))
        if chosen is None:
            raise ToolError(f"{args['ref']} has no option with value or label {args['value']!r}")

    return await _act(args, tab, f"selected {args['value']!r} in {args['ref']}", select)


async def _check(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    element = await ref_element(tab, args["ref"])
    wanted = args.get("checked", True)

    async def check() -> None:
        if await element.is_checked() != wanted:
            await element.click(human=_human(args))
        if await element.is_checked() != wanted:
            raise ToolError(f"{args['ref']} did not become {'checked' if wanted else 'unchecked'}")

    state = "checked" if wanted else "unchecked"
    return await _act(args, tab, f"{args['ref']} {state}", check)


async def _hover(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    element = await ref_element(tab, args["ref"])
    return await _act(args, tab, f"hovering {args['ref']}", element.hover)


async def _scroll(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    if "ref" in args:
        element = await ref_element(tab, args["ref"])

        def action():
            return element.scroll_into_view(human=_human(args))

        what = f"scrolled to {args['ref']}"
    else:
        amount = args.get("amount", SCROLL_DEFAULT)
        delta = -amount if args.get("direction") == "up" else amount

        def action():
            return tab.scroll(delta_y=delta, x=200, y=200, human=_human(args))

        what = f"scrolled {'up' if delta < 0 else 'down'} {abs(delta)}px"
    return await _act(args, tab, what, action)


async def _download(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    timeout = args.get("timeout", DOWNLOAD_DEFAULT)
    if not 0 < timeout <= DOWNLOAD_MAX:
        raise ToolError(f"timeout must be between 0 and {DOWNLOAD_MAX} seconds")
    element = await ref_element(tab, args["ref"])
    async with tab.expect_download(timeout=timeout) as info:
        await element.click(human=_human(args))
    download = await info.value
    folder = pool.config.downloads_dir
    target = await asyncio.to_thread(_free_path, folder, download.suggested_filename)
    saved = await download.save_as(target, timeout=timeout)
    size = await asyncio.to_thread(lambda: saved.stat().st_size)
    data = {
        "targetId": args["targetId"],
        "ok": True,
        "path": str(saved),
        "filename": saved.name,
        "url": download.url,
        "bytes": size,
    }
    return Reply(f"downloaded {saved.name} ({size} bytes) to {saved}", data)


def _free_path(folder: Path, suggested: str) -> Path:
    """``folder/<name>`` not yet taken: ``report.csv``, ``report (1).csv``, …"""
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(suggested).name or "download"
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, n = folder / name, 0
    while candidate.exists():
        n += 1
        candidate = folder / f"{stem} ({n}){suffix}"
    return candidate


_REF = param("string", "Element ref from the latest snapshot, e.g. 'e12'.")
_HUMAN = param("boolean", "Human-like mouse and keyboard (default true).")

TOOLS = [
    Tool("click", "Click an element.", _click, {"ref": _REF, "human": _HUMAN}, ("ref",), page=True),
    Tool(
        "fill",
        "Replace the value of a text field with text; submit presses Enter after.",
        _fill,
        {
            "ref": _REF,
            "text": param("string", "Text to type."),
            "submit": param("boolean", "Press Enter after typing."),
            "human": _HUMAN,
        },
        ("ref", "text"),
        page=True,
    ),
    Tool(
        "press",
        "Press a key or combo ('Enter', 'Control+a'), in the focused element or in ref.",
        _press,
        {"key": param("string", "Key or combo."), "ref": _REF},
        ("key",),
        page=True,
    ),
    Tool(
        "select-option",
        "Choose an option of a <select> by value or visible label.",
        _select_option,
        {"ref": _REF, "value": param("string", "Option value or label.")},
        ("ref", "value"),
        page=True,
    ),
    Tool(
        "check",
        "Set a checkbox or radio (checked true by default).",
        _check,
        {"ref": _REF, "checked": param("boolean", "Wanted state."), "human": _HUMAN},
        ("ref",),
        page=True,
    ),
    Tool("hover", "Move the mouse over an element.", _hover, {"ref": _REF}, ("ref",), page=True),
    Tool(
        "scroll",
        "Scroll an element into view (ref), or the page up/down by amount pixels.",
        _scroll,
        {
            "ref": _REF,
            "direction": param("string", "Page direction.", enum=["up", "down"]),
            "amount": param("integer", f"Pixels (default {SCROLL_DEFAULT})."),
            "human": _HUMAN,
        },
        page=True,
    ),
    Tool(
        "download",
        "Click a ref that starts a download, wait for it and return the saved file's path.",
        _download,
        {
            "ref": _REF,
            "timeout": param("number", f"Seconds (default {DOWNLOAD_DEFAULT})."),
            "human": _HUMAN,
        },
        ("ref",),
        page=True,
        timeout=2 * DOWNLOAD_MAX + 30,
    ),
]

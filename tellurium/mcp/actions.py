"""Tools that act on a snapshot ref: click, fill, press, select-option, check,
hover, scroll, download. Input is human-like unless ``human: false``.

An action returns ``{ok, url, title, navigated}``, not a new snapshot: the
agent asks for one when it needs it.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from tellurium.browser.tab import Tab
from tellurium.mcp import keys, page_state
from tellurium.mcp.pages import ref_element, state_data
from tellurium.mcp.results import Reply, ToolError
from tellurium.mcp.tool import Tool, param

DOWNLOAD_DEFAULT = 60
DOWNLOAD_MAX = 600
SCROLL_DEFAULT = 600

# The option wanted, by value, else by the visible label (the snapshot shows labels):
# [selected index, wanted index], or null.
_FIND = """function() {
  const wanted = __WANTED__;
  const options = Array.from(this.options || []);
  let i = options.findIndex(o => o.value === wanted);
  if (i < 0) i = options.findIndex(o => o.label.trim() === wanted.trim());
  return i < 0 ? null : [this.selectedIndex, i];
}"""
_SELECTED = "function() { return this.selectedIndex; }"
_SET = """function() {
  this.selectedIndex = __INDEX__;
  this.dispatchEvent(new Event('input', {bubbles: true}));
  this.dispatchEvent(new Event('change', {bubbles: true}));
}"""
# Farther than this, a person would type rather than press arrows: set it directly.
MAX_ARROWS = 20


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
            await keys.press(tab, "Enter", human=_human(args))

    return await _act(args, tab, f"filled {args['ref']}", fill)


async def _press(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    keys.parse(args["key"])  # an unknown key fails before anything happens

    async def press() -> None:
        if "ref" in args:
            await (await ref_element(tab, args["ref"])).focus()
        await keys.press(tab, args["key"], human=_human(args))

    return await _act(args, tab, f"pressed {args['key']}", press)


async def _select_option(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    element = await ref_element(tab, args["ref"])

    async def select() -> None:
        found = await element.apply(_FIND.replace("__WANTED__", json.dumps(args["value"])))
        if found is None:
            raise ToolError(f"{args['ref']} has no option with value or label {args['value']!r}")
        current, wanted = found
        if _human(args) and abs(wanted - current) <= MAX_ARROWS:
            current = await _select_with_arrows(tab, element, current, wanted)
        if current != wanted:
            await element.apply(_SET.replace("__INDEX__", str(int(wanted))))

    return await _act(args, tab, f"selected {args['value']!r} in {args['ref']}", select)


async def _select_with_arrows(tab: Tab, element: Any, current: int, wanted: int) -> int:
    """Focus the <select> and press arrows, as a person on a closed list does: the
    browser itself changes the value and fires trusted events. The index reached
    (short of *wanted* when a disabled option or the list's end stops it)."""
    await element.focus()
    key = "ArrowDown" if wanted > current else "ArrowUp"
    while current != wanted:
        await keys.press(tab, key)
        moved = await element.apply(_SELECTED)
        if moved == current:
            break
        current = moved
        await asyncio.sleep(random.uniform(0.05, 0.15))
    return current


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
    try:
        saved = await download.save_as(target, timeout=timeout)
    except BaseException:
        await asyncio.to_thread(target.unlink, missing_ok=True)  # give the name back
        raise
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
    """Reserve ``folder/<name>``: ``report.csv``, else ``report (1).csv``, … The
    file is created empty and exclusively, so two downloads never get one name."""
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(suggested).name
    if name in ("", ".", ".."):
        name = "download"
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, n = folder / name, 0
    while True:
        try:
            with open(candidate, "x"):
                return candidate
        except FileExistsError:
            n += 1
            candidate = folder / f"{stem} ({n}){suffix}"


_REF = param("string", "Snapshot ref, e.g. e12.")
_HUMAN = param("boolean", "Default true.")

TOOLS = [
    Tool("click", "Click an element.", _click, {"ref": _REF, "human": _HUMAN}, ("ref",), page=True),
    Tool(
        "fill",
        "Replace a text field's value; submit presses Enter.",
        _fill,
        {
            "ref": _REF,
            "text": param("string"),
            "submit": param("boolean"),
            "human": _HUMAN,
        },
        ("ref", "text"),
        page=True,
    ),
    Tool(
        "press",
        "Press a key or combo ('Enter', 'Control+a') in the focused element or ref.",
        _press,
        {"key": param("string"), "ref": _REF},
        ("key",),
        page=True,
    ),
    Tool(
        "select-option",
        "Choose a <select> option by value or label.",
        _select_option,
        {"ref": _REF, "value": param("string")},
        ("ref", "value"),
        page=True,
    ),
    Tool(
        "check",
        "Set a checkbox or radio (checked: default true).",
        _check,
        {"ref": _REF, "checked": param("boolean"), "human": _HUMAN},
        ("ref",),
        page=True,
    ),
    Tool("hover", "Move the mouse over an element.", _hover, {"ref": _REF}, ("ref",), page=True),
    Tool(
        "scroll",
        "Scroll ref into view, or the page by amount px.",
        _scroll,
        {
            "ref": _REF,
            "direction": param("string", enum=["up", "down"]),
            "amount": param("integer", f"Default {SCROLL_DEFAULT}."),
            "human": _HUMAN,
        },
        page=True,
    ),
    Tool(
        "download",
        "Click a ref that starts a download; returns the saved path.",
        _download,
        {
            "ref": _REF,
            "timeout": param("number", f"Seconds, default {DOWNLOAD_DEFAULT}."),
            "human": _HUMAN,
        },
        ("ref",),
        page=True,
        timeout=2 * DOWNLOAD_MAX + 30,
    ),
]

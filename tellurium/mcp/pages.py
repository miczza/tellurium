"""Tools that read or move a page: navigate, snapshot, get-text, screenshot,
wait-for, eval. Each takes the ``targetId`` of a tab."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from tellurium.browser.element import Element
from tellurium.browser.tab import Tab
from tellurium.mcp import page_state
from tellurium.mcp.results import Reply, ToolError
from tellurium.mcp.tool import Tool, param

SNAPSHOT_CHARS = 30_000
TEXT_CHARS = 20_000
WAIT_DEFAULT = 10
WAIT_MAX = 120
_REF = re.compile(r"@?e\d+")
_BODY_TEXT = "document.body ? document.body.innerText : ''"


async def ref_element(tab: Tab, ref: str) -> Element:
    """The element of snapshot *ref* (``e3`` or ``@e3``)."""
    if not _REF.fullmatch(ref):
        raise ToolError(f"ref must look like 'e12' (from snapshot), got {ref!r}")
    return await tab.select(ref if ref.startswith("@") else f"@{ref}")


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n[truncated: {len(text) - limit} more chars]"


def state_data(target_id: str, state: page_state.PageState, **extra: Any) -> dict[str, Any]:
    return {"targetId": target_id, "url": state.url, "title": state.title, **extra}


def _timeout(args: dict[str, Any]) -> float:
    seconds = args.get("timeout", WAIT_DEFAULT)
    if not 0 < seconds <= WAIT_MAX:
        raise ToolError(f"timeout must be between 0 and {WAIT_MAX} seconds")
    return float(seconds)


def _one_of(args: dict[str, Any], *names: str) -> str:
    given = [n for n in names if n in args]
    if len(given) != 1:
        raise ToolError(f"pass exactly one of {', '.join(names)}")
    return given[0]


async def _navigate(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    how = _one_of(args, "url", "history")
    before = await page_state.read_or_none(tab)
    if how == "url":
        await tab.get(args["url"], timeout=30)
    elif args["history"] == "back":
        await tab.back()
    elif args["history"] == "forward":
        await tab.forward()
    else:
        await tab.reload()
    state, navigated = await page_state.after_action(
        tab, before, settle=0.0 if how == "url" else 0.3
    )
    data = state_data(args["targetId"], state, ok=True, navigated=navigated)
    return Reply(f"at {state.url} ({state.title})", data)


async def _snapshot(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    text = await tab.snapshot(
        interactive=args.get("interactive", False),
        selector=args.get("selector"),
        depth=args.get("depth"),
        max_chars=args.get("maxChars", SNAPSHOT_CHARS),
    )
    state = await page_state.read_or_none(tab) or page_state.PageState(tab.url, tab.title)
    header = f"# {state.title} - {state.url}"
    return Reply(f"{header}\n{text}", state_data(args["targetId"], state))


async def _get_text(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    if "ref" in args:
        text = await (await ref_element(tab, args["ref"])).text()
    else:
        text = await tab.eval(_BODY_TEXT, timeout=15) or ""
    limit = args.get("maxChars", TEXT_CHARS)
    return Reply(truncate(text, limit), {"targetId": args["targetId"], "chars": len(text)})


async def _screenshot(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    if "ref" in args:
        image = await (await ref_element(tab, args["ref"])).screenshot()
    else:
        image = await tab.screenshot(full_page=args.get("fullPage", False), timeout=30)
    state = await page_state.read_or_none(tab) or page_state.PageState(tab.url, tab.title)
    data = state_data(args["targetId"], state, bytes=len(image))
    return Reply(f"screenshot of {state.url}", data, image=image)


async def _wait_for(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    how = _one_of(args, "text", "ref", "url")
    timeout = _timeout(args)
    if how == "text":
        await tab.find(args["text"], timeout=timeout)
    elif how == "url":
        await tab.wait_for_url(args["url"], timeout=timeout)
    else:
        await _wait_visible(tab, args["ref"], timeout)
    state = await page_state.read_or_none(tab) or page_state.PageState(tab.url, tab.title)
    return Reply(f"found {how}: {args[how]}", state_data(args["targetId"], state, ok=True))


async def _wait_visible(tab: Tab, ref: str, timeout: float) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    element = await ref_element(tab, ref)
    while not await element.is_visible():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"{ref} did not become visible within {timeout:g}s")
        await asyncio.sleep(0.2)


async def _eval(pool: Any, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    try:
        value = await tab.eval(args["expression"], timeout=30)
    except RuntimeError as exc:  # the page threw
        raise ToolError(f"JavaScript error: {exc}") from None
    text = json.dumps(value, ensure_ascii=False, default=str)
    return Reply(truncate(text, TEXT_CHARS), {"targetId": args["targetId"], "value": value})


_REF_PARAM = param("string", "Element ref from the latest snapshot, e.g. 'e12'.")
_MAX_CHARS = param("integer", "Cut the text after this many characters.")

TOOLS = [
    Tool(
        "navigate",
        "Load url in the tab, or go back/forward/reload (history). Returns url, title "
        "and whether the document changed; take a new snapshot after.",
        _navigate,
        {
            "url": param("string", "Address to load."),
            "history": param("string", "History step.", enum=["back", "forward", "reload"]),
        },
        page=True,
    ),
    Tool(
        "snapshot",
        "The page as an accessibility tree, one node per line; act on [ref=eN] with "
        "the other tools. Refs stay valid until the page navigates.",
        _snapshot,
        {
            "interactive": param("boolean", "Only nodes you can act on (much shorter)."),
            "selector": param("string", "CSS selector: snapshot only that part."),
            "depth": param("integer", "Levels of nesting to include."),
            "maxChars": _MAX_CHARS,
        },
        page=True,
    ),
    Tool(
        "get-text",
        "Visible text of an element (ref) or of the whole page.",
        _get_text,
        {"ref": _REF_PARAM, "maxChars": _MAX_CHARS},
        page=True,
    ),
    Tool(
        "screenshot",
        "PNG screenshot of the viewport, the full page, or one element (ref).",
        _screenshot,
        {"ref": _REF_PARAM, "fullPage": param("boolean", "Whole page, not just the viewport.")},
        page=True,
    ),
    Tool(
        "wait-for",
        "Wait until text appears, a ref becomes visible, or the URL matches "
        "(glob with * or substring).",
        _wait_for,
        {
            "text": param("string", "Visible text to wait for."),
            "ref": _REF_PARAM,
            "url": param("string", "URL glob ('*/done*') or substring."),
            "timeout": param("number", f"Seconds (default {WAIT_DEFAULT}, max {WAIT_MAX})."),
        },
        page=True,
        timeout=WAIT_MAX + 15,
    ),
]

EVAL_TOOL = Tool(
    "eval",
    "Evaluate a JavaScript expression in the page and return its JSON value.",
    _eval,
    {"expression": param("string", "JavaScript expression; promises are awaited.")},
    required=("expression",),
    page=True,
)

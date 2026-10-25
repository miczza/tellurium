"""Tools that read or move a page: navigate, snapshot, get-text, screenshot,
wait-for, eval. Each takes the ``targetId`` of a tab."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from typing import Any

from tellurium.browser.element import Element
from tellurium.browser.tab import Tab
from tellurium.mcp import page_state, urls
from tellurium.mcp.results import Reply, ToolError
from tellurium.mcp.tool import Tool, param

SNAPSHOT_CHARS = 30_000
TEXT_CHARS = 20_000
# Image clients refuse pictures larger than this per side.
SHOT_MAX = 8000
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
        url = urls.check(args["url"], allow_local=pool.config.allow_local_urls)
        await tab.get(url, timeout=30)
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
    note, cropped = "", False
    if "ref" in args:
        image = await (await ref_element(tab, args["ref"])).screenshot()
    elif args.get("fullPage"):
        image, (width, height), cropped = await _full_page(tab)
        if cropped:
            note = f" (cropped to {SHOT_MAX} px per side; the page is {width}x{height})"
    else:
        image = await tab.screenshot(timeout=30)
    state = await page_state.read_or_none(tab) or page_state.PageState(tab.url, tab.title)
    data = state_data(args["targetId"], state, bytes=len(image), cropped=cropped)
    return Reply(f"screenshot of {state.url}{note}", data, image=image)


async def _full_page(tab: Tab) -> tuple[bytes, tuple[int, int], bool]:
    """The whole page as PNG, but at most SHOT_MAX px per side (top-left part):
    image clients refuse larger ones. Also the page size and whether it was cut."""
    metrics = await tab.send_cdp("Page.getLayoutMetrics", {})
    size = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
    width, height = int(size.get("width", 0)) or 1, int(size.get("height", 0)) or 1
    clip = {"x": 0, "y": 0, "width": min(width, SHOT_MAX), "height": min(height, SHOT_MAX)}
    ratio = float(await tab.eval("window.devicePixelRatio", timeout=5) or 1)
    scale = min(1.0, 1 / ratio)  # a HiDPI screen would double the pixels past the cap
    shot = await tab.send_cdp(
        "Page.captureScreenshot",
        {"format": "png", "captureBeyondViewport": True, "clip": {**clip, "scale": scale}},
    )
    cropped = width > SHOT_MAX or height > SHOT_MAX
    return base64.b64decode(shot["data"]), (width, height), cropped


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


_REF_PARAM = param("string", "Snapshot ref, e.g. e12.")
_MAX_CHARS = param("integer")

TOOLS = [
    Tool(
        "navigate",
        "Load url, or step history. Returns url, title, navigated.",
        _navigate,
        {
            "url": param("string"),
            "history": param("string", enum=["back", "forward", "reload"]),
        },
        page=True,
    ),
    Tool(
        "snapshot",
        "The page as an accessibility tree; act on [ref=eN] with the other tools.",
        _snapshot,
        {
            "interactive": param("boolean", "Only actionable nodes."),
            "selector": param("string", "CSS: only that part."),
            "depth": param("integer"),
            "maxChars": _MAX_CHARS,
        },
        page=True,
    ),
    Tool(
        "get-text",
        "Visible text of ref, or of the page.",
        _get_text,
        {"ref": _REF_PARAM, "maxChars": _MAX_CHARS},
        page=True,
    ),
    Tool(
        "screenshot",
        "PNG of the viewport, the full page, or ref.",
        _screenshot,
        {"ref": _REF_PARAM, "fullPage": param("boolean")},
        page=True,
    ),
    Tool(
        "wait-for",
        "Wait for text, a visible ref, or a URL (glob or substring).",
        _wait_for,
        {
            "text": param("string"),
            "ref": _REF_PARAM,
            "url": param("string"),
            "timeout": param("number", f"Seconds, default {WAIT_DEFAULT}."),
        },
        page=True,
        timeout=WAIT_MAX + 15,
    ),
]

EVAL_TOOL = Tool(
    "eval",
    "Evaluate JavaScript in the page; returns its JSON value.",
    _eval,
    {"expression": param("string", "Promises are awaited.")},
    required=("expression",),
    page=True,
)

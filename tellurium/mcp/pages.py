"""Tools that read or move a page: navigate, snapshot, get-text, screenshot,
wait-for, eval. Each takes the ``targetId`` of a tab."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from typing import Any

from tellurium.browser.element import Element
from tellurium.browser.tab import Tab, capture_beyond, full_page_clip
from tellurium.mcp import page_state, screenshots, urls
from tellurium.mcp.results import Reply, ToolError
from tellurium.mcp.tool import Tool, param

SNAPSHOT_CHARS = 30_000
TEXT_CHARS = 20_000
# Image clients refuse pictures larger than this per side.
SHOT_MAX = 8000
# Chrome round trips of a screenshot: one capture, and the page metrics.
CAPTURE_TIMEOUT = 20.0
METRICS_TIMEOUT = 5.0
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
    notes, cropped = [], False
    if "ref" in args:
        element = await ref_element(tab, args["ref"])
        png = await element.screenshot()
        capture = _element_capture(tab, element)
    elif args.get("fullPage"):
        capture, (width, height), cropped = await _full_page(tab)
        png = None
        if cropped:
            notes.append(f"cropped to {SHOT_MAX} px per side; the page is {width}x{height}")
    else:
        png = await tab.screenshot(timeout=CAPTURE_TIMEOUT)
        capture = _viewport_capture(tab)
    shot = await screenshots.fit(capture, limit=screenshots.SHOT_BYTES, png=png)
    if shot.note:
        notes.append(shot.note)
    state = await page_state.read_or_none(tab) or page_state.PageState(tab.url, tab.title)
    data = state_data(
        args["targetId"],
        state,
        bytes=len(shot.data),
        format=shot.format,
        scale=shot.scale,
        cropped=cropped,
    )
    note = f" ({'; '.join(notes)})" if notes else ""
    return Reply(f"screenshot of {state.url}{note}", data, image=shot.data, image_type=shot.mime)


async def _metrics(tab: Tab) -> dict:
    return await asyncio.wait_for(tab.send_cdp("Page.getLayoutMetrics", {}), METRICS_TIMEOUT)


async def _shoot(tab: Tab, fmt: str, quality: int | None, clip: dict | None) -> bytes:
    params: dict[str, Any] = {"format": fmt}
    if quality is not None:
        params["quality"] = quality
    if clip is None:
        capture = tab.send_cdp("Page.captureScreenshot", params)
        shot = await asyncio.wait_for(capture, CAPTURE_TIMEOUT)
    else:  # beyond the viewport; any scrollbar Chrome hides for it is given back
        shot = await capture_beyond(tab, {**params, "clip": clip}, CAPTURE_TIMEOUT)
    return base64.b64decode(shot["data"])


def _viewport_capture(tab: Tab) -> screenshots.Capture:
    async def capture(fmt: str, quality: int | None, scale: float) -> bytes:
        clip = None
        if scale < 1:
            metrics = await _metrics(tab)
            view = metrics.get("cssVisualViewport") or metrics.get("visualViewport") or {}
            clip = {
                "x": view.get("pageX", 0),
                "y": view.get("pageY", 0),
                "width": view.get("clientWidth", 0),
                "height": view.get("clientHeight", 0),
                "scale": scale,
            }
        return await _shoot(tab, fmt, quality, clip)

    return capture


def _element_capture(tab: Tab, element: Element) -> screenshots.Capture:
    async def capture(fmt: str, quality: int | None, scale: float) -> bytes:
        box = await element.bounding_box()
        clip = {k: box[k] for k in ("x", "y", "width", "height")}
        return await _shoot(tab, fmt, quality, {**clip, "scale": scale})

    return capture


async def _full_page(tab: Tab) -> tuple[screenshots.Capture, tuple[int, int], bool]:
    """A capture of the whole page, but at most SHOT_MAX px per side (top-left
    part): image clients refuse larger ones. Also the page size and whether it
    was cut."""
    whole = await full_page_clip(tab, METRICS_TIMEOUT)
    width, height = int(whole["width"]) or 1, int(whole["height"]) or 1
    clip = {"x": 0, "y": 0, "width": min(width, SHOT_MAX), "height": min(height, SHOT_MAX)}
    base = min(1.0, whole["scale"])  # a HiDPI screen would double the pixels past the cap

    async def capture(fmt: str, quality: int | None, scale: float) -> bytes:
        return await _shoot(tab, fmt, quality, {**clip, "scale": base * scale})

    cropped = width > SHOT_MAX or height > SHOT_MAX
    return capture, (width, height), cropped


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
        "PNG of the viewport, the full page, or ref (JPEG when a PNG is over 5 MB).",
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

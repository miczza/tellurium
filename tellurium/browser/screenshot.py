"""Screenshots of a tab: the viewport, or the whole page at its CSS size."""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.tab import Tab

logger = logging.getLogger("tellurium")


async def capture(
    tab: Tab,
    path: str | None = None,
    *,
    full_page: bool = False,
    quality: int | None = None,
    format: str = "png",
    timeout: float | None = None,
) -> bytes:
    """:meth:`Tab.screenshot`: the image bytes, also written to *path* if given."""
    params: dict[str, Any] = {"format": format}
    if quality is not None:
        if format == "png":
            logger.warning(
                "screenshot(quality=%s) ignored: quality only applies to "
                "lossy formats (jpeg, webp), not png.",
                quality,
            )
        else:
            params["quality"] = int(quality)
    if full_page:  # the whole page at its CSS size, also on a HiDPI screen
        params["clip"] = await full_page_clip(tab, timeout)
        result = await capture_beyond(tab, params, timeout)
    else:
        result = await tab._session.send("Page.captureScreenshot", params, timeout=timeout)
    data = base64.b64decode(result["data"])
    if path:
        await asyncio.to_thread(Path(path).write_bytes, data)
    return data


# captureBeyondViewport lays the page out at its full height, without scrollbars, and
# Chrome may leave them hidden until the viewport's scroller is laid out again.
# _RELAYOUT_JS does it, only for a scrollbar that went: it toggles the overflow of the
# element the viewport takes it from (<body>'s while <html>'s is visible: turning off
# <html>'s there would make <body> the scroller and lose the scroll position).
_VIEW_JS = "[innerWidth, innerHeight, devicePixelRatio]"
# the viewport's own scrollbars, on scrollingElement: <body> in quirks mode, where
# <html>'s clientHeight is the document's
_GAPS_JS = (
    "(s => [innerWidth - s.clientWidth, innerHeight - s.clientHeight])"
    "(document.scrollingElement || document.documentElement)"
)
_RELAYOUT_JS = """((gx, gy) => {
  const html = document.documentElement, body = document.body;
  const view = document.scrollingElement || html;
  if (innerWidth - view.clientWidth >= gx && innerHeight - view.clientHeight >= gy) return false;
  const css = getComputedStyle(html), x = scrollX, y = scrollY;
  const own = !body || css.overflowX !== 'visible' || css.overflowY !== 'visible';
  const kept = [...document.adoptedStyleSheets], sheet = new CSSStyleSheet();
  sheet.replaceSync((own ? 'html' : 'body') + ' { overflow: hidden !important; }');
  document.adoptedStyleSheets = [...kept, sheet];
  html.offsetWidth;
  document.adoptedStyleSheets = kept;
  html.offsetWidth;
  if (scrollX !== x || scrollY !== y) scrollTo(x, y);
  return true;
})(%d, %d)"""


async def _isolated_value(tab: Tab, expression: str, timeout: float | None) -> Any:
    """*expression* evaluated in the tab's isolated world, where page JS can neither
    fake nor see it; ``None`` when there is none (never in the page's own world)."""
    from tellurium.stealth._isolated import get_hsim_world

    for _ in range(2):  # a world gone with its document: once more, in a fresh one
        if (world := await get_hsim_world(tab, frame_id=tab._frame_id)) is None:
            return None
        params = {"expression": expression, "returnByValue": True, "contextId": world}
        try:
            res = await tab._session.send("Runtime.evaluate", params, timeout=timeout)
            return res.get("result", {}).get("value")
        except CDPError:
            tab._hsim_worlds.pop(tab._frame_id, None)
    return None


def _numbers(value: Any, highs: tuple[float, ...]) -> list[float] | None:
    """*value* if it is one finite number in ``[0, high]`` per *highs*, else ``None``."""
    if not isinstance(value, list) or len(value) != len(highs):
        return None
    for v, high in zip(value, highs, strict=True):
        if isinstance(v, bool) or not isinstance(v, int | float) or not 0 <= v <= high:
            return None  # NaN and infinities fail the range check too
    return [float(v) for v in value]


async def full_page_clip(tab: Tab, timeout: float | None = None) -> dict[str, float]:
    """The clip of the whole page as ``captureBeyondViewport`` lays it out: no vertical
    scrollbar, so at least ``innerWidth`` wide (CDP also floors the content size under
    a fractional ratio). Its scale undoes ``devicePixelRatio``: the image is CSS size."""
    metrics = await tab._session.send("Page.getLayoutMetrics", {}, timeout=timeout)
    size = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
    view = _numbers(await _isolated_value(tab, _VIEW_JS, timeout), (1e6, 1e6, 20))
    width, height, ratio = view or (0, 0, 1)
    clip = {"x": 0, "y": 0, "width": max(size.get("width", 0), width) or 1}
    return {**clip, "height": max(size.get("height", 0), height) or 1, "scale": 1 / (ratio or 1)}


async def capture_beyond(tab: Tab, params: dict, timeout: float | None = None) -> dict:
    """``Page.captureScreenshot`` with ``captureBeyondViewport``, then any scrollbar it
    hid given back; if the caller is cancelled meanwhile, once Chrome answers, in a
    task of the tab (it ends with the capture's own timeout or the session)."""
    gaps = _numbers(await _isolated_value(tab, _GAPS_JS, timeout), (1000, 1000))
    shot = {**params, "captureBeyondViewport": True}
    sent = asyncio.ensure_future(tab._session.send("Page.captureScreenshot", shot, timeout=timeout))
    try:
        await asyncio.wait([sent])  # a cancellation here leaves the capture running
    finally:
        restore = _restore(tab, sent, gaps, timeout)
        if sent.done():
            await restore
        else:
            task = asyncio.ensure_future(restore)
            tab._background.add(task)
            task.add_done_callback(tab._background.discard)
    return sent.result()


async def _restore(tab: Tab, sent: asyncio.Future, gaps: list | None, timeout: float | None):
    """After the capture *sent*: the scrollbars back, if it hid any."""
    await asyncio.wait([sent])
    if not sent.cancelled():
        sent.exception()  # retrieved: the caller, if still there, gets it from result()
    if gaps is None:
        return
    try:
        await _isolated_value(tab, _RELAYOUT_JS % (gaps[0], gaps[1]), timeout)
    except (CDPError, ConnectionError, TimeoutError) as exc:  # the page went meanwhile
        logger.debug("relayout after a full page capture failed: %s", exc)

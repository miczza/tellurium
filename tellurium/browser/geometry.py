"""Where an element is on the page, read from Chrome's layout, never from page JS.

``DOM.getContentQuads`` answers in CSS pixels of the top-level viewport, also
for a node inside a same-process iframe, and cannot be faked by the page (a
``getBoundingClientRect`` can, and is relative to the node's own frame). A node
without a box — detached by a re-render, hidden, or empty — raises
:class:`StaleElementError`: a pointer action never falls back to (0, 0).
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from tellurium.browser.handles import StaleElementError, send_on_handle

if TYPE_CHECKING:
    from tellurium.browser.element import Element

# The aim point wanders this far from the centre, at most a quarter of the box.
_JITTER = 3.0


def _box(quad: list[float]) -> dict[str, float]:
    xs, ys = quad[0::2], quad[1::2]
    return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}


async def content_box(element: Element) -> dict[str, float]:
    """``{x, y, width, height}`` of *element* in top-level viewport coordinates.

    The largest fragment of a node split over lines wins. Raises
    :class:`StaleElementError` when the node has no box with an area.
    """
    object_id = await element._resolve()
    params = {"objectId": object_id}
    quads = (await send_on_handle(element._session, "DOM.getContentQuads", params)).get("quads")
    boxes = [box for box in map(_box, quads or []) if box["width"] > 0 and box["height"] > 0]
    if not boxes:
        raise StaleElementError(
            "Element has no box on the page (detached by a re-render, hidden or empty)"
        )
    return max(boxes, key=lambda box: box["width"] * box["height"])


def center(box: dict[str, float], jitter: float = 0.0) -> tuple[float, float]:
    """The centre of *box*, moved by up to *jitter* pixels (never out of the box)."""
    dx = min(jitter, box["width"] / 4)
    dy = min(jitter, box["height"] / 4)
    return (
        box["x"] + box["width"] / 2 + random.uniform(-dx, dx),
        box["y"] + box["height"] / 2 + random.uniform(-dy, dy),
    )


def contains(box: dict[str, float], x: float, y: float) -> bool:
    return box["x"] <= x <= box["x"] + box["width"] and box["y"] <= y <= box["y"] + box["height"]


async def human_click(element: Element) -> None:
    """Scroll *element* into view, move the pointer to it like a person, click.

    The box is read again right before the press: if the node was replaced or
    moved while the pointer travelled (a page re-rendering on scroll), the
    press is not sent and :class:`StaleElementError` is raised.
    """
    tab = element._tab
    await element.scroll_into_view()
    x, y = center(await content_box(element), _JITTER)
    await tab._human_action("click")
    await tab.mouse_move(x, y, human=True)
    await asyncio.sleep(random.uniform(0.1, 0.3))  # reaction time
    if not contains(await content_box(element), x, y):
        raise StaleElementError("Element moved while the pointer reached it: click not sent")
    press = {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}
    await tab._dispatch_mouse(press)
    await asyncio.sleep(random.uniform(0.08, 0.15))
    await tab._dispatch_mouse({**press, "type": "mouseReleased"})

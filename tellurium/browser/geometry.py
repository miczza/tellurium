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

from tellurium.browser.handles import HANDLE_TIMEOUT, StaleElementError, send_on_handle
from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.element import Element


class ElementNotHittableError(RuntimeError):
    """Another element is under the element's box (covered, zoomed frame): no pointer
    event was sent."""


# Frames climbed at most from the hit node up to the element's document.
_MAX_FRAMES = 8
# The aim point wanders this far from the centre, at most a quarter of the box.
_JITTER = 3.0
# True when *node* is this element or inside it, or inside one of its <label>s
# with no other control on the way (shadow roots included): a click there
# reaches the element, as a person's would.
_HOLDS = """function(node) {
  const controls = 'a[href],button,input,select,textarea,summary,[tabindex],'
    + '[contenteditable]:not([contenteditable="false"])';
  const roles = /^(button|link|checkbox|radio|switch|menuitem\\w*|tab|option|textbox|combobox|slider)$/;
  const labels = Array.from(this.labels || []);
  let crossed = false;
  for (let n = node; n; n = n.parentNode || (n instanceof ShadowRoot ? n.host : null)) {
    if (n === this) return true;
    if (labels.includes(n)) return !crossed;
    if (n.nodeType === 1 && (n.matches(controls) || roles.test(n.getAttribute('role') || ''))) {
      crossed = true;
    }
  }
  return false;
}"""


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
    await ensure_hit(element, x, y)
    press = {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}
    await tab._dispatch_mouse(press)
    await asyncio.sleep(random.uniform(0.08, 0.15))
    await tab._dispatch_mouse({**press, "type": "mouseReleased"})


async def _send(element: Element, method: str, params: dict) -> dict:
    return await element._session.send(method, params, timeout=HANDLE_TIMEOUT)


async def _holds(element: Element, target: int, node: int, frame_id: str) -> bool:
    """Whether backend node *target* is *node* or holds it, asked in *frame_id*'s isolated
    world (page JS cannot fake ``parentNode`` there); ``False`` across documents."""
    from tellurium.stealth._isolated import get_hsim_world

    tab, context = element._tab, None
    if hasattr(tab, "_hsim_worlds"):
        context = await get_hsim_world(tab, frame_id=frame_id)
    where = {"executionContextId": context} if context else {}
    try:
        ids = []
        for backend in (target, node):
            resolved = await _send(element, "DOM.resolveNode", {"backendNodeId": backend, **where})
            ids.append(resolved["object"]["objectId"])
        call = {"objectId": ids[0], "functionDeclaration": _HOLDS, "returnByValue": True}
        answer = await _send(
            element, "Runtime.callFunctionOn", call | {"arguments": [{"objectId": ids[1]}]}
        )
    except CDPError:  # different documents or worlds: not inside
        return False
    finally:
        for object_id in ids:
            await element._session.send("Runtime.releaseObject", {"objectId": object_id})
    return answer.get("result", {}).get("value") is True


async def _describe(element: Element, backend: int) -> str:
    try:
        node = (await _send(element, "DOM.describeNode", {"backendNodeId": backend}))["node"]
    except CDPError:
        return "another node"
    attributes = dict(
        zip(node.get("attributes", [])[::2], node.get("attributes", [])[1::2], strict=False)
    )
    label = node.get("localName") or node.get("nodeName", "node").lower()
    for key in ("id", "class"):
        if attributes.get(key):
            label += f' {key}="{attributes[key][:40]}"'
    return f"<{label}>"


async def ensure_hit(element: Element, x: float, y: float) -> None:
    """Raise :class:`ElementNotHittableError` unless the node Chrome hit-tests at (x, y),
    as a click would (``pointer-events: none`` let through), is *element*, one of its
    labels, or inside them (through frames and shadow roots)."""
    point = {"x": round(x), "y": round(y)}
    hit = await _send(
        element,
        "DOM.getNodeForLocation",
        point | {"includeUserAgentShadowDOM": True, "ignorePointerEventsNone": False},
    )
    target = (await _send(element, "DOM.describeNode", {"objectId": await element._resolve()}))[
        "node"
    ]["backendNodeId"]
    node, frame_id = hit["backendNodeId"], hit.get("frameId", "")
    parents = None
    for _ in range(_MAX_FRAMES):
        if node == target or await _holds(element, target, node, frame_id):
            return
        if parents is None:  # climb from a frame's document to its <iframe>
            tree = (await _send(element, "Page.getFrameTree", {}))["frameTree"]
            parents = _parents(tree)
        if not parents.get(frame_id):
            break
        owner = await _send(element, "DOM.getFrameOwner", {"frameId": frame_id})
        node, frame_id = owner["backendNodeId"], parents[frame_id]
    raise ElementNotHittableError(
        f"Element is not under the pointer at ({x:.0f}, {y:.0f}):"
        f" {await _describe(element, hit['backendNodeId'])} is on top"
        " (covered, or inside a zoomed frame): no event sent"
    )


def _parents(tree: dict, parent: str = "") -> dict[str, str]:
    """frame id -> parent frame id ("" for the top frame)."""
    frame_id = tree["frame"]["id"]
    out = {frame_id: parent}
    for child in tree.get("childFrames", []):
        out |= _parents(child, frame_id)
    return out

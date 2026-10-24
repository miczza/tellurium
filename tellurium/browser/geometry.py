"""Where an element is on the page, read from Chrome's layout, never from page JS.

``DOM.getContentQuads`` answers in CSS pixels of the top-level viewport, also
for a node inside a same-process iframe, and cannot be faked by the page (a
``getBoundingClientRect`` can, and is relative to the node's own frame). A
cross-site iframe (OOPIF) has its own session, whose quads are relative to that
frame: the content box of its ``<iframe>`` in the parent document is added, up
to the tab. A node without a box — detached by a re-render, hidden, or empty —
raises :class:`StaleElementError`: a pointer action never falls back to (0, 0).
"""

from __future__ import annotations

import asyncio
import random
import weakref
from typing import TYPE_CHECKING, Any

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


# Each OOPIF session read so far -> (the session of its parent frame, its frame id).
_LINKS: weakref.WeakKeyDictionary[Any, tuple[Any, str]] = weakref.WeakKeyDictionary()


def alive(session: Any) -> bool:
    """Whether *session* still reaches its target (not detached, browser not closed)."""
    return getattr(session, "_closed_error", None) is None


def link_frame(child: Any, parent: Any, frame_id: str) -> None:
    """Record that *child* is the session of the cross-site frame *frame_id*, whose
    ``<iframe>`` lives in *parent*'s document: its boxes are offset by that iframe's."""
    _LINKS[child] = (parent, frame_id)


def linked_session(frame_id: str) -> Any | None:
    """The live session recorded for the cross-site frame *frame_id*, if any."""
    found = (child for child, (_, frame) in list(_LINKS.items()) if frame == frame_id)
    return next((child for child in found if alive(child)), None)


def _chain(session: Any) -> list[tuple[Any, Any, str]]:
    """``(session, parent session, frame id)`` of each cross-site frame from *session*
    up to the tab, innermost first; empty for the tab's own session."""
    chain: list[tuple[Any, Any, str]] = []
    while (link := _LINKS.get(session)) is not None and len(chain) < _MAX_FRAMES:
        chain.append((session, *link))
        session = link[0]
    return chain


def _box(quad: list[float]) -> dict[str, float]:
    xs, ys = quad[0::2], quad[1::2]
    return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}


async def _largest_box(session: Any, params: dict, what: str) -> dict[str, float]:
    """The largest fragment of a node's content box in *session*'s frame coordinates."""
    quads = (await send_on_handle(session, "DOM.getContentQuads", params)).get("quads")
    boxes = [box for box in map(_box, quads or []) if box["width"] > 0 and box["height"] > 0]
    if not boxes:
        raise StaleElementError(
            f"{what} has no box on the page (detached by a re-render, hidden or empty)"
        )
    return max(boxes, key=lambda box: box["width"] * box["height"])


async def _zoom(session: Any) -> float:
    """CSS pixels to device-independent pixels in *session*'s frame (CSS zoom included)."""
    metrics = await send_on_handle(session, "Page.getLayoutMetrics", {})
    return float(metrics.get("cssVisualViewport", {}).get("zoom") or 1.0)


async def _frame_owner(child: Any, parent: Any, frame_id: str) -> tuple[int, dict, float]:
    """Backend id and content box (in *parent*'s frame) of the ``<iframe>`` of *frame_id*,
    and the scale from *child*'s CSS pixels to *parent*'s (a CSS zoom on the way)."""
    owner = await send_on_handle(parent, "DOM.getFrameOwner", {"frameId": frame_id})
    backend = owner["backendNodeId"]
    # the frame's document starts inside border and padding: the box model's content quad
    # (getContentQuads gives an <iframe>'s border box)
    model = await send_on_handle(parent, "DOM.getBoxModel", {"backendNodeId": backend})
    box = _box(model["model"]["content"])
    if box["width"] <= 0 or box["height"] <= 0:
        raise StaleElementError("Element's frame has no box on the page (hidden or empty)")
    child_zoom, parent_zoom = await asyncio.gather(_zoom(child), _zoom(parent))
    return backend, box, child_zoom / parent_zoom


async def content_box(element: Element) -> dict[str, float]:
    """``{x, y, width, height}`` of *element* in top-level viewport coordinates.

    The largest fragment of a node split over lines wins. Raises
    :class:`StaleElementError` when the node, or the iframe holding it, has no box
    with an area.
    """
    object_id = await element._resolve()
    box = await _largest_box(element._session, {"objectId": object_id}, "Element")
    for link in _chain(element._session):
        _, frame, scale = await _frame_owner(*link)
        box = {
            "x": frame["x"] + box["x"] * scale,
            "y": frame["y"] + box["y"] * scale,
            "width": box["width"] * scale,
            "height": box["height"] * scale,
        }
    return box


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
    from tellurium.browser.refs import frame_world

    tab, context = element._tab, None
    if hasattr(tab, "_hsim_worlds"):
        context = await frame_world(tab, element._session, frame_id)
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


async def _describe(session: Any, hit: dict | None) -> str:
    if hit is None:
        return "no element"
    backend = hit["backendNodeId"]
    try:
        node = await session.send(
            "DOM.describeNode", {"backendNodeId": backend}, timeout=HANDLE_TIMEOUT
        )
        node = node["node"]
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


async def _hit(session: Any, x: float, y: float) -> dict | None:
    """The node *session*'s frame hit-tests at (x, y) of its viewport, as a click would;
    ``None`` when there is none. Chrome takes document coordinates: the scroll is added."""
    view = (await send_on_handle(session, "Page.getLayoutMetrics", {})).get("cssLayoutViewport")
    point = {
        "x": round(x + (view or {}).get("pageX", 0)),
        "y": round(y + (view or {}).get("pageY", 0)),
    }
    params = point | {"includeUserAgentShadowDOM": True, "ignorePointerEventsNone": False}
    try:
        return await session.send("DOM.getNodeForLocation", params, timeout=HANDLE_TIMEOUT)
    except CDPError:  # "No node found at given location": outside the page
        return None


def _not_hittable(x: float, y: float, on_top: str) -> ElementNotHittableError:
    return ElementNotHittableError(
        f"Element is not under the pointer at ({x:.0f}, {y:.0f}): {on_top} is on top"
        " (covered, or inside a zoomed frame): no event sent"
    )


async def ensure_hit(element: Element, x: float, y: float) -> None:
    """Raise :class:`ElementNotHittableError` unless the node Chrome hit-tests at (x, y),
    as a click would (``pointer-events: none`` let through), is *element*, one of its
    labels, or inside them (through frames and shadow roots). Across a cross-site frame
    each document on the way must hit the ``<iframe>`` that leads to the element."""
    top_x, top_y = x, y
    for link in reversed(_chain(element._session)):  # from the tab down
        owner, frame, scale = await _frame_owner(*link)
        parent = link[1]
        hit = await _hit(parent, x, y)
        if hit is None or hit["backendNodeId"] != owner:
            raise _not_hittable(top_x, top_y, await _describe(parent, hit))
        x, y = (x - frame["x"]) / scale, (y - frame["y"]) / scale
    hit = await _hit(element._session, x, y)
    if hit is None:
        raise _not_hittable(top_x, top_y, "no element")
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
    raise _not_hittable(top_x, top_y, await _describe(element._session, hit))


def _parents(tree: dict, parent: str = "") -> dict[str, str]:
    """frame id -> parent frame id ("" for the top frame)."""
    frame_id = tree["frame"]["id"]
    out = {frame_id: parent}
    for child in tree.get("childFrames", []):
        out |= _parents(child, frame_id)
    return out

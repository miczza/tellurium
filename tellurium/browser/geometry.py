"""Where an element is on the page, read from Chrome's layout, never from page JS.

``DOM.getContentQuads`` answers in CSS pixels of the top-level viewport, also
for a node inside a same-process iframe, and cannot be faked by the page (a
``getBoundingClientRect`` can, and is relative to the node's own frame). A
cross-site iframe (OOPIF) has its own session, whose quads are relative to that
frame: they are mapped, up to the tab, through the projective map of each
``<iframe>``'s box (border, padding, CSS zoom, 2D and 3D transforms alike); a frame
seen edge-on takes no pointer action. A node without a box — detached by a re-render, hidden, or empty —
raises :class:`StaleElementError`: a pointer action never falls back to (0, 0).
"""

from __future__ import annotations

import asyncio
import random
import weakref
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from tellurium.browser.handles import HANDLE_TIMEOUT, StaleElementError, send_on_handle
from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.element import Element


class ElementNotHittableError(RuntimeError):
    """Another element is under the element's box (covered, zoomed frame): no pointer
    event was sent."""


# The devicePixelRatio of this frame if the node is in its document, else null.
_HELD = "function() { return this.ownerDocument === document ? devicePixelRatio : null; }"
# Seconds a release of a handle may take: best effort, never worth a long wait.
_RELEASE = 2.0
# Frames climbed at most from the hit node up to the element's document.
_MAX_FRAMES = 8
# A frame scaled below this area per CSS pixel² (edge-on, scale(0)) takes no clicks.
_MIN_DET = 1e-3
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


def link_frame(child: Any, parent: Any, frame_id: str) -> None:
    """Record that *child* is the session of the cross-site frame *frame_id*, whose
    ``<iframe>`` lives in *parent*'s document: its boxes are offset by that iframe's."""
    _LINKS[child] = (parent, frame_id)


def frame_chain(session: Any) -> list[tuple[Any, Any, str]]:
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


def _area(quad: list[float]) -> float:
    """Area of a quad (shoelace): 0 for one seen edge-on."""
    xs, ys = quad[0::2], quad[1::2]
    return abs(sum(xs[i] * ys[i - 1] - xs[i - 1] * ys[i] for i in range(len(xs)))) / 2


async def _largest_quad(session: Any, params: dict, what: str) -> list[float]:
    """The largest fragment of a node's content quad in *session*'s frame coordinates."""
    quads = (await send_on_handle(session, "DOM.getContentQuads", params)).get("quads")
    quads = [quad for quad in quads or [] if _area(quad) > 0]
    if not quads:
        raise StaleElementError(
            f"{what} has no box on the page (detached by a re-render, hidden or empty)"
        )
    return max(quads, key=_area)


class _Homography:
    """The projective map from a cross-site frame's own CSS pixels to its parent frame's
    viewport: ``(x, y, w) = M (u, v, 1)``, the point ``(x / w, y / w)``. It carries the
    ``<iframe>``'s border, padding, CSS zoom, 2D and 3D transforms (perspective,
    ``matrix3d``) at once: a projective map is fixed by where four corners go."""

    def __init__(self, m: tuple[float, ...]) -> None:
        self.m = m  # row major, 3x3

    @classmethod
    def of_rect(cls, width: float, height: float, quad: list[tuple[float, float]]) -> _Homography:
        """The map taking the corners of the rectangle (0, 0)-(*width*, *height*), clockwise
        from the top left, to the four points of *quad*."""
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
        sx, sy = x0 - x1 + x2 - x3, y0 - y1 + y2 - y3
        dx1, dx2, dy1, dy2 = x1 - x2, x3 - x2, y1 - y2, y3 - y2
        den = dx1 * dy2 - dx2 * dy1
        if abs(den) < 1e-12:
            raise _degenerate()
        g, h = (sx * dy2 - dx2 * sy) / den, (dx1 * sy - sx * dy1) / den
        a, b, d, e = x1 - x0 + g * x1, x3 - x0 + h * x3, y1 - y0 + g * y1, y3 - y0 + h * y3
        # the unit square's map, after scaling the rectangle down to it
        return cls((a / width, b / height, x0, d / width, e / height, y0, g / width, h / height, 1))

    def then_after(self, du: float, dv: float) -> _Homography:
        """This map applied after moving a point by (*du*, *dv*)."""
        a, b, c, d, e, f, g, h, i = self.m
        return _Homography(
            (a, b, a * du + b * dv + c, d, e, d * du + e * dv + f, g, h, g * du + h * dv + i)
        )

    def apply(self, u: float, v: float) -> tuple[float, float]:
        a, b, c, d, e, f, g, h, i = self.m
        w = g * u + h * v + i
        if w <= 0:  # behind the viewer: not on the screen
            raise _degenerate()
        return (a * u + b * v + c) / w, (d * u + e * v + f) / w

    def invert(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f, g, h, i = self.m
        adjugate = (
            e * i - f * h, c * h - b * i, b * f - c * e,
            f * g - d * i, a * i - c * g, c * d - a * f,
            d * h - e * g, b * g - a * h, a * e - b * d,
        )  # fmt: skip
        det = a * adjugate[0] + b * adjugate[3] + c * adjugate[6]
        if abs(det) < 1e-12:
            raise _degenerate()
        # the inverse itself, not only the adjugate: a frame turned over (scaleX(-1))
        # has a negative determinant, which would flip the sign of w
        return _Homography(tuple(k / det for k in adjugate)).apply(x, y)


def _degenerate() -> ElementNotHittableError:
    return ElementNotHittableError("Element's frame is seen edge-on: no event sent")


def _convex(points: list[tuple[float, float]]) -> bool:
    """Whether the four *points* turn the same way at each corner (no bow tie)."""
    turns = []
    for i, (x0, y0) in enumerate(points):
        (x1, y1), (x2, y2) = points[(i + 1) % 4], points[(i + 2) % 4]
        turns.append((x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1))
    return all(t > 0 for t in turns) or all(t < 0 for t in turns)


def _corners(quad: list[float]) -> list[tuple[float, float]]:
    return list(zip(quad[0::2], quad[1::2], strict=True))


async def _frame_map(tab: Any, child: Any, parent: Any, frame_id: str) -> tuple[int, _Homography]:
    """Backend id (in *parent*) of the ``<iframe>`` of *frame_id*, and the projective
    map from *child*'s CSS pixels to *parent*'s viewport. Raises
    :class:`ElementNotHittableError` when the frame is seen edge-on (no area, or
    folded): no map gives where a point of it is on the screen."""
    owner = await send_on_handle(parent, "DOM.getFrameOwner", {"frameId": frame_id})
    backend = owner["backendNodeId"]
    # the model's width and height are the untransformed border box in the <iframe>'s
    # own (zoomed) CSS pixels, as the document's are; its quads are where that box is,
    # divided by the zoom of the frame holding the <iframe>: multiplied back here
    model = (await send_on_handle(parent, "DOM.getBoxModel", {"backendNodeId": backend}))["model"]
    width, height = model["width"], model["height"]
    if min(width, height) <= 0:
        raise StaleElementError("Element's frame has no box on the page (hidden or empty)")
    zoom = await _holder_zoom(tab, parent, backend)
    border = [(x * zoom, y * zoom) for x, y in _corners(model["border"])]
    if not _convex(border) or _area(model["border"]) * zoom**2 < _MIN_DET * width * height:
        raise _degenerate()
    outer = _Homography.of_rect(width, height, border)
    # the frame's document starts at the content box's corner (inside border and padding)
    corner = _corners(model["content"])[0]
    left, top = outer.invert(corner[0] * zoom, corner[1] * zoom)
    return backend, outer.then_after(left, top)


async def _holder_zoom(tab: Any, parent: Any, owner: int) -> float:
    """The zoom of the frame whose document holds the ``<iframe>`` *owner* (backend id in
    *parent*), relative to *parent*'s root. Raises :class:`ElementNotHittableError` when
    it cannot be read: a map off by an unknown zoom would send the click elsewhere."""
    if (zoom := await _node_zoom(tab, parent, lambda: _known(owner))) is None:
        raise ElementNotHittableError(
            "The zoom of the frame holding the element's frame cannot be read: no event sent"
        )
    return zoom


async def _known(node: int) -> int:
    return node


async def _node_zoom(tab: Any, session: Any, node_of: Callable[[], Awaitable[int]]) -> float | None:
    """How many of *session*'s root-frame CSS pixels one CSS pixel of the frame holding
    the backend node ``await node_of()`` (asked only when there are frames) is: Chrome divides a node's quads by the zoom of its frame (a CSS
    zoom on an ancestor of a same-process ``<iframe>``). Each ``devicePixelRatio`` is read
    in that frame's isolated world, where page JS cannot fake it, so a frame of another
    origin than the root's is read too; ``None`` when it cannot be."""
    tree = (await send_on_handle(session, "Page.getFrameTree", {}))["frameTree"]
    frames = list(_parents(tree))  # the root first; cross-site frames are not in it
    if len(frames) == 1:  # no same-process frame: the root holds it
        return 1.0
    node = await node_of()
    for frame_id in frames:
        if (own := await _ratio_if_holding(tab, session, frame_id, node)) is None:
            continue
        if frame_id == frames[0]:
            return 1.0
        base = await _pixel_ratio(tab, session, frames[0])
        return own / base if base else None
    return None


async def _ratio_if_holding(tab: Any, session: Any, frame_id: str, node: int) -> float | None:
    """``devicePixelRatio`` of *frame_id* if its document holds backend node *node*, asked
    in the frame's isolated world; ``None`` otherwise or when it cannot be asked."""
    from tellurium.browser.refs import frame_world

    if tab is None or (context := await frame_world(tab, session, frame_id)) is None:
        return None
    where = {"backendNodeId": node, "executionContextId": context}
    try:
        resolved = (await send_on_handle(session, "DOM.resolveNode", where))["object"]
    except CDPError:  # another origin's node, or a world gone with its document
        tab._hsim_worlds.pop(frame_id, None)
        return None
    if (object_id := resolved.get("objectId")) is None:
        return None
    call = {"objectId": object_id, "functionDeclaration": _HELD, "returnByValue": True}
    try:
        value = (await send_on_handle(session, "Runtime.callFunctionOn", call))["result"]
    except CDPError:
        return None
    finally:
        await session.send("Runtime.releaseObject", {"objectId": object_id}, timeout=_RELEASE)
    value = value.get("value")
    ok = isinstance(value, int | float) and not isinstance(value, bool) and value > 0
    return float(value) if ok else None


async def _pixel_ratio(tab: Any, session: Any, frame_id: str) -> float | None:
    """``devicePixelRatio`` of *frame_id*, read in the tab's isolated world there (made
    once more if the cached one went with its document); ``None`` when it cannot be."""
    from tellurium.browser.refs import frame_world

    for _ in range(2):
        if tab is None or (context := await frame_world(tab, session, frame_id)) is None:
            return None
        params = {"expression": "devicePixelRatio", "contextId": context, "returnByValue": True}
        try:
            value = (await send_on_handle(session, "Runtime.evaluate", params))["result"]
        except CDPError:  # the world went with its document
            tab._hsim_worlds.pop(frame_id, None)
            continue
        value = value.get("value")
        ok = isinstance(value, int | float) and not isinstance(value, bool) and value > 0
        return float(value) if ok else None
    return None


async def _zoom(element: Element) -> float:
    """:func:`_node_zoom` of *element*; 1 when it cannot be read (the hit test, in the
    element's own session, then refuses a point off the element)."""

    async def node_of() -> int:
        params = {"objectId": await element._resolve()}
        return (await _send(element, "DOM.describeNode", params))["node"]["backendNodeId"]

    return await _node_zoom(element._tab, element._session, node_of) or 1.0


async def content_box(element: Element) -> dict[str, float]:
    """``{x, y, width, height}`` of *element* in top-level viewport coordinates.

    The largest fragment of a node split over lines wins; the quad is scaled back by
    the CSS zoom of the same-process frames on the way, and across cross-site frames
    the box bounds the node's quad as the frames turn, scale and tilt it. Raises
    :class:`StaleElementError` when the node, or the iframe holding it, has no box
    with an area, :class:`ElementNotHittableError` when a frame on the way is seen
    edge-on.
    """
    object_id = await element._resolve()
    quad = await _largest_quad(element._session, {"objectId": object_id}, "Element")
    zoom = await _zoom(element)
    points = [(x * zoom, y * zoom) for x, y in _corners(quad)]
    for link in frame_chain(element._session):
        _, affine = await _frame_map(element._tab, *link)
        points = [affine.apply(*point) for point in points]
    return _box([coordinate for point in points for coordinate in point])


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
            if "objectId" not in resolved["object"]:  # another origin's node: not reachable
                return False
            ids.append(resolved["object"]["objectId"])
        call = {"objectId": ids[0], "functionDeclaration": _HOLDS, "returnByValue": True}
        answer = await _send(
            element, "Runtime.callFunctionOn", call | {"arguments": [{"objectId": ids[1]}]}
        )
    except CDPError:  # different documents or worlds: not inside
        return False
    finally:
        for object_id in ids:
            release = {"objectId": object_id}
            await element._session.send("Runtime.releaseObject", release, timeout=_RELEASE)
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
    for link in reversed(frame_chain(element._session)):  # from the tab down
        owner, affine = await _frame_map(element._tab, *link)
        parent = link[1]
        hit = await _hit(parent, x, y)
        if hit is None or hit["backendNodeId"] != owner:
            raise _not_hittable(top_x, top_y, await _describe(parent, hit))
        x, y = affine.invert(x, y)
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

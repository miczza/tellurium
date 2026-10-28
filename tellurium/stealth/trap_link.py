"""Trap links: links a person could not see or click right now, or that wear a honeypot marker.

A crawler that follows every ``<a href>`` of a page also follows the ones a site
hides from people to catch bots. :func:`reasons` reads, in the tab's isolated world
(page JS can neither patch what it reads nor see the call), the link's computed
style, boxes, ancestors and attributes, and names the signals that fired:

``not-rendered``
    no box: ``display: none`` on it or an ancestor, or inside a closed
    ``<details>`` (a link of a closed menu is a trap too: a person does not click it
    without opening the menu first);
``visibility-hidden``, ``transparent``
    ``visibility`` other than ``visible``; less than 5% of it showing through the
    ``opacity`` and ``filter: opacity()`` of it and its ancestors multiplied, or a
    ``mask-image`` of gradients with no color that is not transparent;
``no-pointer``, ``inert``, ``aria-hidden``
    ``pointer-events: none``; inside an ``inert`` subtree; ``aria-hidden="true"``
    on it or an ancestor while it can still be clicked;
``zero-size``
    less than 2 CSS px wide or tall, its overflowing content included unless it
    clips it;
``off-page``
    wholly outside what scrolling can reach, through every box that scrolls it,
    inner to outer (``left: -9999px``); outside the viewport when ``position:
    fixed`` or along an axis the page does not scroll (``overflow: hidden`` on the
    root, as while a modal is open). Below the fold of the page or of an app's own
    scroll box, a slide further along a carousel: not off-page;
``clipped``
    nothing of it left inside the boxes of the ancestors that clip it
    (``overflow: hidden``, ``contain: paint``/``strict``/``content``, ``clip``, a
    ``clip-path`` basic shape: ``inset()``, ``circle(0)``, ``ellipse()``, a
    ``polygon()`` of no area);
``covered``
    in the viewport, yet no point of it hit-tests (``elementFromPoint``, as a click
    would) to it or its content: a box on top, or under a block's background with
    ``z-index: -1``. Not looked at where it would take a scroll to be seen;
``empty``
    nothing a person could see in its box: no text, no image, icon, pseudo-element
    content, background image or color, border;
``same-color``
    all its visible text is transparent or the color of the background behind it,
    when that background is known: never over an image, a gradient, a positioned
    ``::before``/``::after`` overlay or another element painting under the text;
``honeypot-marker``
    ``honeypot`` (also ``honey-pot``, ``honey_pot``) in its ``id``, ``class`` or ``name``;
``nofollow``
    ``rel="nofollow"``, reported only next to another signal: alone it is a
    normal link.

A hidden link (off the page, clipped away, too small, transparent) that its
``:focus``, ``:focus-visible`` or ``:focus-within`` rules bring back, as a "skip to
content" link, is not a trap. The rules are read from the sheets the page can read
(``@import``, ``@media``, ``@supports``, ``@layer`` and nesting followed), never
applied: nothing is fetched, no transition starts, the focus does not move. Only the
values they declare count, and only for what hides the link: ``left``/``top`` that
bring it back on the page, ``clip: auto``, ``clip-path: none``, a size or a
``font-size`` again, an ``opacity`` above zero; ``a:focus { transform: ... }``
brings nothing back. A cross-origin sheet, a rule an inline style beats, a link out
of the tab order: it stays a trap. Conservative: better to skip a closed menu's link
than to click a trap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tellurium.browser.handles import handles_of, send_on_handle
from tellurium.cdp.types import CDPError
from tellurium.stealth.extension import load_script

if TYPE_CHECKING:
    from tellurium.browser.element import Element

# Run with ``this`` bound to the link (or, with ``frame``, an ``<iframe>`` holding it), in
# the isolated world; returns ``{reasons, nofollow, framed}``.
_REASONS_JS = load_script("trap_link.js")
_OWNER_DOCUMENT_JS = "function () { return this.ownerDocument; }"
_MAX_FRAMES = 16


class NoIsolatedWorldError(RuntimeError):
    """The link's frame has no isolated world, so the check would be visible to the page."""


async def reasons(element: Element) -> list[str]:
    """The trap signals of *element* (an ``<a>``) that fired; empty for a normal link.

    One ``Runtime.callFunctionOn`` in the isolated world of the element's frame; inside a
    frame, one more for each ``<iframe>`` up to the tab (an OOPIF's in its parent's
    session): a frame a person cannot see hides the links in it. Its signals follow the
    link's own. :class:`NoIsolatedWorldError` when a frame on the way has no isolated
    world: the check never runs where the page could see it.
    """
    session, tab = element._session, element._tab
    object_id = await element._resolve()
    described = await send_on_handle(session, "DOM.describeNode", {"objectId": object_id})
    frame_id = element._frame_id or await _root_frame(tab, session)
    found, document = await _check(tab, session, frame_id, described["node"]["backendNodeId"])
    signals = [signal for signal in found["reasons"] if signal != "nofollow"]
    for _hop in range(_MAX_FRAMES):
        if document is None or (owner := await _owner(session, document)) is None:
            break
        session, backend = owner
        frame_id = await _root_frame(tab, session)
        held, document = await _check(tab, session, frame_id, backend, frame=True)
        signals += [signal for signal in held["reasons"] if signal not in signals]
    return signals + ["nofollow"] if signals and found["nofollow"] else signals


async def is_trap_link(element: Element) -> bool:
    """Whether a person could not see or click *element* now, or it wears a honeypot marker."""
    return bool(await reasons(element))


async def _check(
    tab: Any, session: Any, frame_id: str, backend: int, *, frame: bool = False
) -> tuple[dict, int | None]:
    """The check of node *backend* in *frame_id*'s isolated world, and, when that node is
    itself inside a frame, the backend id of its document (``None`` at the top)."""
    target = await _isolated(tab, session, frame_id, backend)
    if target is None:
        raise NoIsolatedWorldError("no isolated world in the link's frame: trap check not run")
    handles = handles_of(tab)
    try:
        call = {"objectId": target, "functionDeclaration": _REASONS_JS, "returnByValue": True}
        call["arguments"] = [{"value": frame}]
        found = _value(await send_on_handle(session, "Runtime.callFunctionOn", call))
        if not found.get("framed"):
            return found, None
        own = {"objectId": target, "functionDeclaration": _OWNER_DOCUMENT_JS}
        document = (await send_on_handle(session, "Runtime.callFunctionOn", own))["result"]
        try:
            where = {"objectId": document["objectId"]}
            node = (await send_on_handle(session, "DOM.describeNode", where))["node"]
        finally:
            if handles is not None:
                handles.discard(document["objectId"], session)
        return found, node["backendNodeId"]
    finally:
        if handles is not None:
            handles.discard(target, session)


async def _owner(session: Any, document: int) -> tuple[Any, int] | None:
    """The ``<iframe>`` holding *document* of *session*: the session it lives in and its
    backend id; ``None`` for the tab's own document."""
    from tellurium.browser.geometry import frame_chain

    tree = (await send_on_handle(session, "Page.getFrameTree", {}))["frameTree"]
    frames, children = [], list(tree.get("childFrames", []))
    while children:
        child = children.pop()
        frames.append(child["frame"]["id"])
        children += child.get("childFrames", [])
    for frame_id in frames:
        try:
            owner = await send_on_handle(session, "DOM.getFrameOwner", {"frameId": frame_id})
            where = {"backendNodeId": owner["backendNodeId"]}
            node = (await send_on_handle(session, "DOM.describeNode", where))["node"]
        except CDPError:  # a frame that went meanwhile
            continue
        if node.get("contentDocument", {}).get("backendNodeId") == document:
            return session, owner["backendNodeId"]
    if not (hops := frame_chain(session)):
        return None
    _, parent, frame_id = hops[0]  # an OOPIF's root document: its <iframe> is in the parent's
    owner = await send_on_handle(parent, "DOM.getFrameOwner", {"frameId": frame_id})
    return parent, owner["backendNodeId"]


def _value(answer: dict) -> Any:
    remote = answer.get("result", {})
    if remote.get("subtype") == "error" or "exceptionDetails" in answer:
        raise RuntimeError(remote.get("description", "trap-link check failed"))
    return remote.get("value")


async def _isolated(tab: Any, session: Any, frame_id: str, backend: int) -> str | None:
    """Node *backend* resolved in *frame_id*'s isolated world, or ``None``."""
    from tellurium.browser.refs import frame_world

    if not hasattr(tab, "_hsim_worlds"):
        return None
    params: dict[str, Any] = {"backendNodeId": backend}
    if (handles := handles_of(tab)) is not None:
        params["objectGroup"] = handles.name
    for _attempt in range(2):  # a world cached for a document that has gone: make a new one
        context = await frame_world(tab, session, frame_id)
        if context is None:
            return None
        try:
            where = params | {"executionContextId": context}
            resolved = await send_on_handle(session, "DOM.resolveNode", where)
        except CDPError:
            tab._hsim_worlds.pop(frame_id, None)
            continue
        return resolved["object"]["objectId"]
    return None


async def _root_frame(tab: Any, session: Any) -> str:
    """The frame *session* addresses: the tab's, or an OOPIF's own root."""
    if session is tab._session:
        return tab._frame_id
    tree = await send_on_handle(session, "Page.getFrameTree", {})
    return str(tree["frameTree"]["frame"]["id"])

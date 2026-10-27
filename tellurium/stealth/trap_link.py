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
    ``visibility`` other than ``visible``; ``opacity: 0`` on it or an ancestor;
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
    (``overflow: hidden``, ``clip``, a ``clip-path`` basic shape: ``inset()``,
    ``circle(0)``, ``ellipse()``, a ``polygon()`` of no area);
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

A hidden link (off the page, clipped away, transparent) in sight while Chrome
forces ``:focus`` on it, as a "skip to content" link, is not a trap: the focused
state is measured, not the rules. With a transition or an animation on the way, or
out of the tab order, it stays one. Conservative, with no thresholds to tune: better
to skip a closed menu's link than to click a trap.
"""

from __future__ import annotations

import asyncio
import contextlib
import weakref
from typing import TYPE_CHECKING, Any

from tellurium.browser.handles import handles_of, send_on_handle
from tellurium.cdp.types import CDPError
from tellurium.stealth.extension import load_script

if TYPE_CHECKING:
    from tellurium.browser.element import Element
    from tellurium.cdp.transport._session import Session

# One forced-focus check at a time per CDP session (CSS.disable ends them all).
_FOCUS_LOCKS: weakref.WeakKeyDictionary[Session, asyncio.Lock] = weakref.WeakKeyDictionary()

# Run with ``this`` bound to the link, in the isolated world; returns the signals.
_REASONS_JS = load_script("trap_link.js")


class NoIsolatedWorldError(RuntimeError):
    """The link's frame has no isolated world, so the check would be visible to the page."""


async def reasons(element: Element) -> list[str]:
    """The trap signals of *element* (an ``<a>``) that fired; empty for a normal link.

    One ``Runtime.callFunctionOn`` in the isolated world of the element's frame, and a
    second one under a forced ``:focus`` when a focus rule might bring a hidden link back.
    :class:`NoIsolatedWorldError` when that frame has no isolated world: the check never
    runs where the page could see it.
    """
    session, tab = element._session, element._tab
    object_id = await element._resolve()
    target = await _isolated(element, object_id)
    if target is None:
        raise NoIsolatedWorldError("no isolated world in the link's frame: trap check not run")
    try:
        found = _value(await send_on_handle(session, "Runtime.callFunctionOn", _call(target)))
        if isinstance(found, dict):
            found = found["revealed"] if await _seen_focused(session, target) else found["reasons"]
    finally:
        if (handles := handles_of(tab)) is not None:
            handles.discard(target, session)
    return list(found or [])


def _call(target: str, *, focused: bool = False) -> dict:
    args = {"arguments": [{"value": focused}], "returnByValue": True}
    return {"objectId": target, "functionDeclaration": _REASONS_JS} | args


def _value(answer: dict) -> Any:
    remote = answer.get("result", {})
    if remote.get("subtype") == "error" or "exceptionDetails" in answer:
        raise RuntimeError(remote.get("description", "trap-link check failed"))
    return remote.get("value")


async def _seen_focused(session: Session, target: str) -> bool:
    """Whether the link is in sight while Chrome forces ``:focus`` and ``:focus-visible`` on it.

    ``CSS.forcePseudoState`` only changes which rules match: focus does not move, no focus or
    blur event fires, nothing scrolls. Force, measure and release go out back to back, so the
    state lasts one round trip; ``CSS.disable`` drops what is left. One at a time per session.
    """
    async with _FOCUS_LOCKS.setdefault(session, asyncio.Lock()):
        node = (await send_on_handle(session, "DOM.requestNode", {"objectId": target}))["nodeId"]
        await send_on_handle(session, "CSS.enable", {})
        try:
            force = {"nodeId": node, "forcedPseudoClasses": ["focus", "focus-visible"]}
            steps = [
                ("CSS.forcePseudoState", force),
                ("Runtime.callFunctionOn", _call(target, focused=True)),
                ("CSS.forcePseudoState", force | {"forcedPseudoClasses": []}),
            ]
            forced, answer, _ = await asyncio.gather(
                *(send_on_handle(session, method, params) for method, params in steps),
                return_exceptions=True,
            )
        finally:
            with contextlib.suppress(CDPError, TimeoutError, ConnectionError):
                await send_on_handle(session, "CSS.disable", {})
    if isinstance(answer, BaseException):
        raise answer
    return not isinstance(forced, BaseException) and bool(_value(answer).get("seen"))


async def is_trap_link(element: Element) -> bool:
    """Whether a person could not see or click *element* now, or it wears a honeypot marker."""
    return bool(await reasons(element))


async def _isolated(element: Element, object_id: str) -> str | None:
    """*element*'s node resolved in its frame's isolated world, or ``None``."""
    from tellurium.browser.refs import frame_world

    session, tab = element._session, element._tab
    if not hasattr(tab, "_hsim_worlds"):
        return None
    described = await send_on_handle(session, "DOM.describeNode", {"objectId": object_id})
    params = {"backendNodeId": described["node"]["backendNodeId"]}
    if (handles := handles_of(tab)) is not None:
        params["objectGroup"] = handles.name
    frame_id = await _frame_of(element)
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


async def _frame_of(element: Element) -> str:
    """The frame the element's session addresses: the tab's, or an OOPIF's own root."""
    session, tab = element._session, element._tab
    if element._frame_id:
        return element._frame_id
    if session is tab._session:
        return tab._frame_id
    tree = await send_on_handle(session, "Page.getFrameTree", {})
    return str(tree["frameTree"]["frame"]["id"])

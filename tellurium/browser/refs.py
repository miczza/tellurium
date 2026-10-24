"""Element refs of a tab: ``e3`` ↔ DOM node, stable within one document.

A snapshot labels each node it shows with a short ref (``[ref=e3]``) that an
agent hands back to act on the node. The :class:`RefMap` of a tab keeps the
mapping ``ref ↔ backendDOMNodeId``:

* the same node keeps the same ref across snapshots of the same document;
* a main-frame navigation starts a new *generation*: every ref issued before
  it raises :class:`StaleElementError`;
* ref numbers are never reused within a tab, so an old ref can never land on
  a node of a later document (backend ids may repeat across renderers).

A ref resolves with ``DOM.resolveNode`` into the tab's handle group, giving a
normal :class:`Element`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from tellurium.browser.handles import (
    HANDLE_TIMEOUT,
    StaleElementError,
    handles_of,
    send_on_handle,
)
from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.element import Element
    from tellurium.browser.snapshot import SnapshotNode
    from tellurium.browser.tab import Tab
    from tellurium.cdp.transport._session import Session

_IS_CONNECTED = "function() { return this.isConnected; }"
_BY_VALUE = {"returnByValue": True}
_REF = re.compile(r"@?e([1-9][0-9]*)")


def parse_ref(text: str) -> str | None:
    """``"e3"`` for ``"e3"`` or ``"@e3"``; ``None`` if *text* is not a ref."""
    match = _REF.fullmatch(text.strip())
    return f"e{match.group(1)}" if match else None


def pending_ref(backend_node_id: int, frame_id: str = "") -> str:
    """A placeholder ref, settled later by :meth:`RefMap.settle`."""
    return f"#{backend_node_id}#{frame_id}"


class RefMap:
    """Per-tab map of refs to backend DOM node ids, one generation per document."""

    def __init__(self) -> None:
        self._generation = 0
        self._next = 1  # number of the next ref handed out
        self._first = 1  # first ref number of the current generation
        self._ref_of: dict[int, int] = {}  # backendDOMNodeId -> ref number
        self._node_of: dict[int, int] = {}  # ref number -> backendDOMNodeId
        self._frame_of: dict[int, str] = {}  # ref number -> frame id ("" unknown)

    @property
    def generation(self) -> int:
        """Bumped by every :meth:`reset` (main-frame navigation)."""
        return self._generation

    def ref_for(self, backend_node_id: int, frame_id: str = "") -> str:
        """The ref of *backend_node_id* (in frame *frame_id*), new on first sight."""
        number = self._ref_of.get(backend_node_id)
        if number is None:
            number, self._next = self._next, self._next + 1
            self._ref_of[backend_node_id] = number
            self._node_of[number] = backend_node_id
        if frame_id:
            self._frame_of[number] = frame_id
        return f"e{number}"

    def frame_of(self, ref: str) -> str:
        """The frame id of the node behind *ref*, ``""`` if not known."""
        parsed = parse_ref(ref)
        return self._frame_of.get(int(parsed[1:]), "") if parsed else ""

    def lookup(self, ref: str) -> int:
        """The backend node id of *ref* (``"e3"`` or ``"@e3"``).

        :class:`StaleElementError` if the ref belongs to a previous document,
        ``LookupError`` if it was never handed out (or is not a ref).
        """
        parsed = parse_ref(ref)
        if parsed is None:
            raise LookupError(f"{ref!r} is not an element ref (expected e.g. 'e3' or '@e3')")
        number = int(parsed[1:])
        node = self._node_of.get(number)
        if node is not None:
            return node
        if number < self._first:
            raise StaleElementError(
                f"Ref {parsed} belongs to a previous document: take a new snapshot"
            )
        raise LookupError(f"No element with ref {parsed}: take a snapshot first")

    def settle(self, nodes: list[SnapshotNode]) -> None:
        """Swap the :func:`pending_ref` refs of a snapshot built off the event loop for
        real ones, in document order (the map itself is only touched on the loop)."""
        for node in nodes:
            if node.ref and node.ref.startswith("#"):
                backend_node_id, frame_id = node.ref[1:].split("#", 1)
                node.ref = self.ref_for(int(backend_node_id), frame_id)
            self.settle(node.children)

    def reset(self) -> None:
        """Start a new generation: every ref handed out so far turns stale."""
        self._generation += 1
        self._first = self._next
        self._ref_of.clear()
        self._node_of.clear()
        self._frame_of.clear()

    def on_frame_navigated(self, params: dict) -> None:
        """``Page.frameNavigated`` handler: reset on a main-frame navigation."""
        if not params.get("frame", {}).get("parentId"):
            self.reset()


async def _connected(
    session: Session, tab: Tab | Any, backend_node_id: int, frame_id: str, object_id: str
) -> bool:
    """``isConnected`` read in the tab's isolated world, where page JS cannot redefine
    it; in the page's own world only when no isolated world is available."""
    from tellurium.stealth._isolated import get_hsim_world

    handles, isolated = handles_of(tab), None
    if hasattr(tab, "_hsim_worlds"):
        frame_id = frame_id or getattr(tab, "_frame_id", "")
        context = await get_hsim_world(tab, frame_id=frame_id)
        params: dict[str, Any] = {"backendNodeId": backend_node_id, "executionContextId": context}
        if handles is not None:
            params["objectGroup"] = handles.name
        try:
            if context is not None:
                result = await session.send("DOM.resolveNode", params, timeout=HANDLE_TIMEOUT)
                isolated = result["object"]["objectId"]
        except CDPError:  # the world went with its document: use the page's world
            tab._hsim_worlds.pop(frame_id, None)
    check = {"objectId": isolated or object_id, "functionDeclaration": _IS_CONNECTED}
    try:
        answer = await send_on_handle(session, "Runtime.callFunctionOn", check | _BY_VALUE)
    finally:
        if isolated and handles is not None:
            handles.discard(isolated)
    return answer.get("result", {}).get("value") is True


async def resolve_ref(session: Session, tab: Tab | Any, refs: RefMap, ref: str) -> Element:
    """Resolve *ref* into an :class:`Element` in *tab*'s handle group.

    Raises :class:`StaleElementError` when the ref is from another document,
    or when the document changed while it was being resolved; ``LookupError``
    when the ref does not exist.
    """
    from tellurium.browser.element import Element

    generation = refs.generation
    backend_node_id = refs.lookup(ref)
    params: dict[str, Any] = {"backendNodeId": backend_node_id}
    handles = handles_of(tab)
    if handles is not None:
        params["objectGroup"] = handles.name
    result = await send_on_handle(session, "DOM.resolveNode", params)
    object_id = result["object"]["objectId"]
    try:
        # A node detached by a re-render or document.open() still resolves:
        # acting on it would hit an empty box at (0, 0), i.e. another element.
        if not await _connected(session, tab, backend_node_id, refs.frame_of(ref), object_id):
            raise StaleElementError(
                f"Ref {ref} names a node no longer in the page (re-rendered or removed):"
                " take a new snapshot"
            )
        if refs.generation != generation:  # a navigation committed meanwhile
            raise StaleElementError(
                f"Ref {ref} belongs to a previous document: take a new snapshot"
            )
    except BaseException:
        if handles is not None:
            handles.discard(object_id)
        raise
    return Element(session, tab, object_id=object_id)

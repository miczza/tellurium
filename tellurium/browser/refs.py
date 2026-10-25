"""Element refs of a tab: ``e3`` ↔ DOM node, stable within one document.

A snapshot labels each node it shows with a short ref (``[ref=e3]``) that an
agent hands back to act on the node. The :class:`RefMap` of a tab keeps the
mapping ``ref ↔ backendDOMNodeId``:

* the same node keeps the same ref across snapshots of the same document;
* a main-frame navigation starts a new *generation*: every ref issued before
  it raises :class:`StaleElementError`;
* ref numbers are never reused within a tab, so an old ref can never land on
  a node of a later document (backend ids may repeat across renderers);
* a node of a cross-site iframe (OOPIF) is keyed by its renderer's session too,
  and its ref resolves through that session; it is bound to the frame's document
  (its loader id): once the frame loads another document, in the same renderer or
  in a new one whose backend ids start again, its refs raise
  :class:`StaleElementError` and later snapshots hand out new ones.

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


def pending_ref(backend_node_id: int, frame_id: str = "", owner: str = "") -> str:
    """A placeholder ref, settled later by :meth:`RefMap.settle`."""
    return f"#{backend_node_id}#{frame_id}#{owner}"


class RefMap:
    """Per-tab map of refs to backend DOM node ids, one generation per document."""

    def __init__(self) -> None:
        self._generation = 0
        self._next = 1  # number of the next ref handed out
        self._first = 1  # first ref number of the current generation
        # an owner names the renderer session of a node ("" for the tab's own)
        self._ref_of: dict[tuple[str, int], int] = {}  # (owner, backendDOMNodeId) -> number
        self._node_of: dict[int, tuple[str, int]] = {}  # ref number -> (owner, backend id)
        self._frame_of: dict[int, str] = {}  # ref number -> frame id ("" unknown)
        self._sessions: dict[str, Any] = {}  # owner -> its Session
        self._documents: dict[str, str] = {}  # owner -> loader id of its frame's document
        self._gone: set[int] = set()  # ref numbers of an owner's previous documents

    @property
    def generation(self) -> int:
        """Bumped by every :meth:`reset` (main-frame navigation)."""
        return self._generation

    def ref_for(self, backend_node_id: int, frame_id: str = "", owner: str = "") -> str:
        """The ref of *backend_node_id* (in frame *frame_id*, of the renderer session
        *owner*, ``""`` for the tab's own), new on first sight."""
        key = (owner, backend_node_id)
        number = self._ref_of.get(key)
        if number is None:
            number, self._next = self._next, self._next + 1
            self._ref_of[key] = number
            self._node_of[number] = key
        if frame_id:
            self._frame_of[number] = frame_id
        return f"e{number}"

    def frame_of(self, ref: str) -> str:
        """The frame id of the node behind *ref*, ``""`` if not known."""
        parsed = parse_ref(ref)
        return self._frame_of.get(int(parsed[1:]), "") if parsed else ""

    def bind(self, owner: str, session: Session | Any, document: str = "") -> None:
        """Remember *session* as the renderer session named *owner* in refs, showing the
        document whose loader id is *document*: the refs of another document of the
        same owner turn stale."""
        if self._documents.get(owner, document) != document:
            self.forget(owner)
        self._sessions[owner] = session
        if document:
            self._documents[owner] = document

    def forget(self, owner: str) -> None:
        """Turn stale every ref of the renderer session *owner* (its frame navigated)."""
        for key in [key for key in self._ref_of if key[0] == owner]:
            number = self._ref_of.pop(key)
            self._node_of.pop(number, None)
            self._frame_of.pop(number, None)
            self._gone.add(number)
        self._documents.pop(owner, None)

    def document_of(self, ref: str) -> tuple[str, str]:
        """``(owner, loader id)`` of the document *ref* was handed out in (``""`` unknown)."""
        parsed = parse_ref(ref)
        key = self._node_of.get(int(parsed[1:])) if parsed else None
        owner = key[0] if key else ""
        return owner, self._documents.get(owner, "")

    def session_of(self, ref: str) -> Session | Any | None:
        """The session of the document of *ref*; ``None`` for the tab's own (or unknown)."""
        parsed = parse_ref(ref)
        key = self._node_of.get(int(parsed[1:])) if parsed else None
        return self._sessions.get(key[0]) if key and key[0] else None

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
            return node[1]
        if number < self._first or number in self._gone:
            raise StaleElementError(
                f"Ref {parsed} belongs to a previous document: take a new snapshot"
            )
        raise LookupError(f"No element with ref {parsed}: take a snapshot first")

    def settle(self, nodes: list[SnapshotNode]) -> None:
        """Swap the :func:`pending_ref` refs of a snapshot built off the event loop for
        real ones, in document order (the map itself is only touched on the loop)."""
        for node in nodes:
            if node.ref and node.ref.startswith("#"):
                backend_node_id, frame_id, owner = node.ref[1:].split("#", 2)
                node.ref = self.ref_for(int(backend_node_id), frame_id, owner)
            self.settle(node.children)

    def reset(self) -> None:
        """Start a new generation: every ref handed out so far turns stale."""
        self._generation += 1
        self._first = self._next
        self._ref_of.clear()
        self._node_of.clear()
        self._frame_of.clear()
        self._sessions.clear()
        self._documents.clear()
        self._gone.clear()

    def on_frame_navigated(self, params: dict) -> None:
        """``Page.frameNavigated`` handler: reset on a main-frame navigation."""
        if not params.get("frame", {}).get("parentId"):
            self.reset()


async def frame_world(tab: Tab | Any, session: Session | Any, frame_id: str) -> int | None:
    """The tab's isolated world in *frame_id*, made through *session*: an OOPIF's world
    can only be made by its own session. ``None`` when there is none (page world)."""
    from tellurium.stealth._isolated import _HSIM_WORLD_NAME, get_hsim_world

    if session is getattr(tab, "_session", session) or not frame_id:
        return await get_hsim_world(tab, frame_id=frame_id)
    if (cached := tab._hsim_worlds.get(frame_id)) is not None:
        return cached
    params = {"frameId": frame_id, "worldName": _HSIM_WORLD_NAME, "grantUniversalAccess": False}
    try:
        made = await session.send("Page.createIsolatedWorld", params, timeout=HANDLE_TIMEOUT)
    except (CDPError, ConnectionError, TimeoutError):  # frame gone: the page world
        return None
    if (context := made.get("executionContextId")) is not None:
        tab._hsim_worlds[frame_id] = context
    return context


async def _connected(
    session: Session, tab: Tab | Any, backend_node_id: int, frame_id: str, object_id: str
) -> bool:
    """``isConnected`` read in the tab's isolated world, where page JS cannot redefine
    it; in the page's own world only when no isolated world is available."""
    handles, isolated = handles_of(tab), None
    if hasattr(tab, "_hsim_worlds"):
        frame_id = frame_id or getattr(tab, "_frame_id", "")
        context = await frame_world(tab, session, frame_id)
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
            handles.discard(isolated, session)
    return answer.get("result", {}).get("value") is True


async def _loader(session: Session | Any) -> str:
    """Loader id of the document in the frame of *session* (an OOPIF's own session)."""
    tree = await send_on_handle(session, "Page.getFrameTree", {})
    return str(tree["frameTree"]["frame"].get("loaderId") or "")


async def resolve_ref(session: Session, tab: Tab | Any, refs: RefMap, ref: str) -> Element:
    """Resolve *ref* into an :class:`Element` in *tab*'s handle group.

    *session* is the tab's; a ref of a cross-site iframe resolves through that
    iframe's session. Raises :class:`StaleElementError` when the ref is from
    another document, when the document changed while it was being resolved, or
    when its iframe went away; ``LookupError`` when the ref does not exist.
    """
    from tellurium.browser.element import Element

    generation = refs.generation
    backend_node_id = refs.lookup(ref)
    params: dict[str, Any] = {"backendNodeId": backend_node_id}
    handles = handles_of(tab)
    if handles is not None:
        params["objectGroup"] = handles.name
    own = refs.session_of(ref)
    session = own if own is not None else session
    try:
        result = await send_on_handle(session, "DOM.resolveNode", params)
    except ConnectionError as exc:
        if own is None:
            raise
        # the iframe's renderer session was detached (navigated away or removed)
        raise StaleElementError(
            f"Ref {ref} is in a frame that went away: take a new snapshot"
        ) from exc
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
        owner, document = refs.document_of(ref)
        if own is not None and document and await _loader(own) != document:
            refs.forget(owner)  # the frame loaded another document: backend ids start again
            raise StaleElementError(
                f"Ref {ref} belongs to a previous document of its frame: take a new snapshot"
            )
    except BaseException:
        if handles is not None:
            handles.discard(object_id, session)
        raise
    return Element(session, tab, object_id=object_id)

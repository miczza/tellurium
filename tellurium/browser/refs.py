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

from tellurium.browser.handles import StaleElementError, handles_of, send_on_handle

if TYPE_CHECKING:
    from tellurium.browser.element import Element
    from tellurium.browser.tab import Tab
    from tellurium.cdp.transport._session import Session

_REF = re.compile(r"@?e([1-9][0-9]*)")


def parse_ref(text: str) -> str | None:
    """``"e3"`` for ``"e3"`` or ``"@e3"``; ``None`` if *text* is not a ref."""
    match = _REF.fullmatch(text.strip())
    return f"e{match.group(1)}" if match else None


class RefMap:
    """Per-tab map of refs to backend DOM node ids, one generation per document."""

    def __init__(self) -> None:
        self._generation = 0
        self._next = 1  # number of the next ref handed out
        self._first = 1  # first ref number of the current generation
        self._ref_of: dict[int, int] = {}  # backendDOMNodeId -> ref number
        self._node_of: dict[int, int] = {}  # ref number -> backendDOMNodeId

    @property
    def generation(self) -> int:
        """Bumped by every :meth:`reset` (main-frame navigation)."""
        return self._generation

    def ref_for(self, backend_node_id: int) -> str:
        """The ref of *backend_node_id*, handing out a new one on first sight."""
        number = self._ref_of.get(backend_node_id)
        if number is None:
            number, self._next = self._next, self._next + 1
            self._ref_of[backend_node_id] = number
            self._node_of[number] = backend_node_id
        return f"e{number}"

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

    def reset(self) -> None:
        """Start a new generation: every ref handed out so far turns stale."""
        self._generation += 1
        self._first = self._next
        self._ref_of.clear()
        self._node_of.clear()

    def on_frame_navigated(self, params: dict) -> None:
        """``Page.frameNavigated`` handler: reset on a main-frame navigation."""
        if not params.get("frame", {}).get("parentId"):
            self.reset()


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
    if refs.generation != generation:  # a navigation committed meanwhile
        if handles is not None:
            handles.discard(object_id)
        raise StaleElementError(f"Ref {ref} belongs to a previous document: take a new snapshot")
    return Element(session, tab, object_id=object_id)

"""Accessibility snapshot of a page, compact enough for an LLM.

``Accessibility.getFullAXTree`` (or ``queryAXTree`` for a ``selector=``) gives
the AX nodes; the pure functions of :mod:`~tellurium.browser.snapshot_text` prune
them into :class:`SnapshotNode` trees and render them as lines. Same-process iframes are
stitched under their ``iframe`` node, and so are cross-site ones (OOPIFs), read
through their own session; an OOPIF that cannot be reached shows as
``- iframe "<url>" [oopif]``, one that does not answer within the time left of
``snapshot_timeout`` as ``[oopif: not responding]``, one with more DOM nodes than
``max_nodes`` leaves it as ``[oopif: too large, N nodes]`` (``max_nodes`` bounds the
page's own renderer: over it, an error). Refs come from the tab's
:class:`~tellurium.browser.refs.RefMap`. No ``Runtime.enable``: only the
Accessibility, DOM and Target domains.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from tellurium.browser import geometry
from tellurium.browser.handles import StaleElementError
from tellurium.browser.refs import pending_ref
from tellurium.browser.snapshot_text import SnapshotNode as SnapshotNode  # re-exported
from tellurium.browser.snapshot_text import Unread as _Unread
from tellurium.browser.snapshot_text import ax_props as _props
from tellurium.browser.snapshot_text import ax_role as _role
from tellurium.browser.snapshot_text import build_nodes, render
from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.refs import RefMap
    from tellurium.cdp.transport._session import Session

# Bound of each CDP command of a snapshot; a 5000-node tree answers in ~0.1 s.
SNAPSHOT_TIMEOUT = 30.0
# Default ``max_nodes``: Chrome needs ~1 s and ~50 MB of JSON for 50000 nodes,
# parsed on the event loop by the transport. Over it, ``selector=`` scopes the
# fetch to a subtree. Default ``snapshot_timeout``: bound of the whole fetch.
MAX_DOM_NODES = 50_000
FETCH_TIMEOUT = 5.0
# Iframes nested deeper than this are shown without their content.
_MAX_FRAME_NESTING = 8
# Cross-site iframes must answer within this share of ``snapshot_timeout``: the rest
# is left for building the snapshot of the page around them.
_OOPIF_SHARE = 0.8
# Wait for a cross-site iframe that auto-attach is attaching, before attaching it.
_AUTO_ATTACH_WAIT = 1.0
_DISABLE_TIMEOUT = 0.2  # sent either way: only the wait for the answer is cut


class SnapshotTooLargeError(RuntimeError):
    """The page is over the snapshot size limit: snapshot a part with ``selector=``."""


class _TooLarge(Exception):
    """A cross-site iframe has more DOM nodes than ``max_nodes`` leaves it."""


@dataclass
class _Bounds:
    """What the cross-site iframes of one snapshot may still take: until *deadline*
    (loop time) to answer, *nodes* DOM nodes under ``max_nodes``."""

    deadline: float | None = None
    nodes: float = float("inf")


@dataclass
class AXTree:
    """The AX nodes of one document; *frames* maps an ``<iframe>``'s backend node id
    to its document's tree or its URL (an OOPIF that could not be reached).
    *owner* names the renderer session read (``""``: the one snapshotted),
    *session* is that session, *document* the loader id of an OOPIF's document,
    read before its tree; none of them is in the JSON."""

    nodes: list[dict[str, Any]]
    frames: dict[int, AXTree | str] = field(default_factory=dict)
    owner: str = ""
    session: Any = field(default=None, repr=False, compare=False)
    document: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AXTree:
        frames = data.get("frames", {}).items()
        subs = {int(k): v if isinstance(v, str) else cls.from_json(v) for k, v in frames}
        return cls(nodes=data["nodes"], frames=subs)

    def to_json(self) -> dict[str, Any]:
        subs = {str(k): v if isinstance(v, str) else v.to_json() for k, v in self.frames.items()}
        return {"nodes": self.nodes, "frames": subs}


async def _send(session: Session, method: str, params: dict, timeout: float) -> dict:
    try:
        return await session.send(method, params, timeout=timeout)
    except TimeoutError:
        raise TimeoutError(f"{method} got no answer within {timeout}s") from None


def _document_url(nodes: list[dict[str, Any]]) -> str:
    return str(_props(next((n for n in nodes if _role(n) == "RootWebArea"), {})).get("url") or "")


async def _oopif_session(session: Session, frame_id: str, timeout: float) -> Session:
    """The session of the cross-site iframe *frame_id* under *session*: the one already
    attached (stealth auto-attach, an earlier snapshot), else a new one attached
    through *session*, which Chrome detaches with the frame or the tab. Raises
    ``CDPError``, ``ConnectionError`` or ``TimeoutError``."""
    router = session.router
    child = router.session_for_target(frame_id)
    if child is None and session.auto_attaches:  # Chrome is attaching it for the engine
        child = await router.wait_for_target(frame_id, min(timeout, _AUTO_ATTACH_WAIT))
    if child is None:
        mine = await router.attach(frame_id, via=session, timeout=timeout)
        child = router.session_for_target(frame_id) or mine
        if child is not mine:  # attached meanwhile by someone else: one session per frame
            await router.detach(mine, via=session)
    geometry.link_frame(child, session, frame_id)
    return child


class _Ledger:
    """Admits the cross-site iframes of one document under ``max_nodes`` in document
    order: a counted one waits until those before it are admitted, left out or given
    up on, so which one is left out does not depend on which renderer answers first."""

    def __init__(self, bounds: _Bounds, size: int) -> None:
        loop = asyncio.get_running_loop()
        self._bounds = bounds
        self._counts: dict[int, int | None] = {}
        self._verdicts = [loop.create_future() for _ in range(size)]
        self._next = 0

    def report(self, index: int, count: int | None) -> None:
        """The *index*-th iframe has *count* DOM nodes; ``None``: it takes no budget
        (same-process, gone, not answering). Only the first report of an index counts."""
        self._counts.setdefault(index, count)
        while self._next in self._counts:
            nodes = self._counts[self._next]
            fits = nodes is not None and nodes <= self._bounds.nodes
            if fits:
                self._bounds.nodes -= nodes
            self._verdicts[self._next].set_result(fits)
            self._next += 1

    async def admit(self, index: int, count: int) -> bool:
        """Whether the *index*-th iframe, of *count* nodes, fits what those before leave."""
        self.report(index, count)
        return await asyncio.shield(self._verdicts[index])


async def _oopif_tree(
    session: Session, frame_id: str, sub: dict, slot: tuple[_Ledger, int] | None, within: float
) -> AXTree:
    """The tree of the cross-site iframe *frame_id*, with its document's loader id.
    With a *slot* it is counted first (session included, within *within* s, so a stuck
    renderer does not hold the ones after it) and read only if its ledger admits it."""
    timeout = sub["timeout"]

    async def counted() -> tuple[Session, int]:
        child = await _oopif_session(session, frame_id, timeout)
        return child, await _count_nodes(child, timeout) if slot is not None else 0

    child, count = await asyncio.wait_for(counted(), within if slot is not None else None)
    if slot is not None and not await slot[0].admit(slot[1], count):
        raise _TooLarge(count)
    loaded = await _send(child, "Page.getFrameTree", {}, timeout)
    tree = await fetch_tree(child, **sub, _owner=child.session_id or "")
    tree.document = str(loaded["frameTree"]["frame"].get("loaderId") or "")
    return tree


async def _frame_of(
    session: Session, bid: int, base_url: str, owner: str, sub: dict, slot: Any
) -> AXTree | str | None:
    """The document of the ``<iframe>`` with backend id *bid*: tree, OOPIF URL or ``None``.
    *sub* holds the :func:`fetch_tree` options of the frame; an OOPIF has until the
    deadline of its ``_bounds`` to answer, its nested frames included. *slot* is its
    place in the ledger of its document (``None``: no node budget)."""
    try:
        return await _frame_in(session, bid, base_url, owner, sub, slot)
    finally:
        if slot is not None:  # not read across sites: those after it need not wait
            slot[0].report(slot[1], None)


async def _frame_in(
    session: Session, bid: int, base_url: str, owner: str, sub: dict, slot: Any
) -> AXTree | str | None:
    timeout, bounds = sub["timeout"], sub["_bounds"]
    try:
        described = await _send(session, "DOM.describeNode", {"backendNodeId": bid}, timeout)
    except CDPError:  # detached meanwhile
        return None
    node = described.get("node", {})
    if not (frame_id := node.get("frameId")):
        return None
    if sub["_nesting"] > _MAX_FRAME_NESTING:  # too deep: shown without content
        return None
    if "contentDocument" in node and slot is not None:  # same renderer: no budget of its own
        slot[0].report(slot[1], None)
    if "contentDocument" not in node:  # the document lives in another renderer
        attributes = node.get("attributes", [])
        src = dict(zip(attributes[::2], attributes[1::2], strict=False)).get("src", "")
        url = urljoin(base_url, src) if src else "about:blank"
        deadline = bounds.deadline if bounds else None
        left = timeout if deadline is None else deadline - asyncio.get_running_loop().time()
        left = max(left, 0)
        try:
            read = _oopif_tree(session, frame_id, sub, slot, left / 2)
            return await asyncio.wait_for(read, left)
        except TimeoutError:  # a renderer stuck in a loop
            return _Unread(url, "not responding")
        except _TooLarge as large:  # an ad of 1e5 nodes: left out, the page still shows
            return _Unread(url, f"too large, {large.args[0]} nodes")
        except (CDPError, ConnectionError, KeyError):
            return url
    try:
        return await fetch_tree(session, frame_id=frame_id, **sub, _owner=owner)
    except CDPError:  # the frame went away between the two calls
        return None


async def fetch_tree(
    session: Session,
    *,
    frame_id: str | None = None,
    root: int | None = None,
    timeout: float = SNAPSHOT_TIMEOUT,
    _nesting: int = 0,
    _owner: str = "",
    _bounds: _Bounds | None = None,
) -> AXTree:
    """Fetch the AX tree of a document (the main frame by default) and its iframes,
    cross-site ones too; with *root* (a backend node id) only that node's subtree
    (``queryAXTree``)."""
    if root is not None:
        method, params = "Accessibility.queryAXTree", {"backendNodeId": root}
    else:
        method, params = "Accessibility.getFullAXTree", {"frameId": frame_id} if frame_id else {}
    result = await _send(session, method, params, timeout)
    nodes = result.get("nodes", [])
    frames = [n for n in nodes if _role(n) == "Iframe" and not n.get("ignored")]
    iframes = [bid for n in frames if (bid := n.get("backendDOMNodeId"))]
    tree, base_url = AXTree(nodes=nodes, owner=_owner, session=session), _document_url(nodes)
    if iframes:
        sub = {"timeout": timeout, "_nesting": _nesting + 1, "_bounds": _bounds}
        limited = _bounds is not None and _bounds.nodes != float("inf")
        ledger = _Ledger(_bounds, len(iframes)) if limited else None
        subs = await asyncio.gather(
            *(
                _frame_of(session, b, base_url, _owner, sub, (ledger, i) if ledger else None)
                for i, b in enumerate(iframes)
            )
        )
        tree.frames = {bid: f for bid, f in zip(iframes, subs, strict=True) if f is not None}
    return tree


async def _backend_id_of(session: Session, selector: str, timeout: float) -> int:
    doc = await _send(session, "DOM.getDocument", {"depth": 0}, timeout)
    query = {"nodeId": doc["root"]["nodeId"], "selector": selector}
    node_id = (await _send(session, "DOM.querySelector", query, timeout)).get("nodeId", 0)
    if not node_id:
        raise LookupError(f"No element matching {selector!r}")
    described = await _send(session, "DOM.describeNode", {"nodeId": node_id}, timeout)
    return described["node"]["backendNodeId"]


async def _count_nodes(session: Session, timeout: float) -> int:
    """Nodes of the live documents and their iframes, by Chrome: no garbage, no page JS."""
    await _send(session, "DOM.getDocument", {"depth": 0}, timeout)
    search = await _send(session, "DOM.performSearch", {"query": "//node()"}, timeout)
    await _send(session, "DOM.discardSearchResults", {"searchId": search["searchId"]}, timeout)
    return search["resultCount"]


def _too_large(count: int, what: str, max_nodes: int) -> SnapshotTooLargeError:
    return SnapshotTooLargeError(
        f"{what} has {count} DOM nodes, over max_nodes={max_nodes}: pass selector= to"
        " snapshot a part, or a higher max_nodes= (None: no limit)"
    )


async def _snapshot_once(
    session: Session, selector: str | None, limits: tuple, timeout: float, **opts: Any
) -> tuple[list[SnapshotNode], dict[str, tuple[Session, str]]]:
    """One snapshot and the OOPIF sessions read, by owner, within ``snapshot_timeout``
    from the first command: shadow roots escape the node count, and a renderer busy
    with an earlier tree delays them all."""
    deadline = asyncio.get_running_loop().time() + limits[1] * _OOPIF_SHARE
    seen: dict[str, Any] = {"count": "no", "scope": None, "sessions": {}, "deadline": deadline}
    steps = _steps(session, selector, limits[0], seen, timeout, opts)
    try:
        return await asyncio.wait_for(steps, limits[1]), seen["sessions"]
    except TimeoutError:
        hint = "a narrower selector= or " if seen["scope"] else ""
        raise SnapshotTooLargeError(
            f"The snapshot took over snapshot_timeout={limits[1]:g} s ({seen['count']} DOM nodes"
            f" counted; shadow DOM is not): pass {hint}a higher snapshot_timeout="
        ) from None


def _sessions_of(tree: AXTree) -> dict[str, tuple[Session, str]]:
    """The OOPIF sessions read for *tree* and the loader id of their documents, by owner."""
    found = {tree.owner: (tree.session, tree.document)} if tree.owner else {}
    for sub in tree.frames.values():
        if isinstance(sub, AXTree):
            found |= _sessions_of(sub)
    return found


async def _steps(
    session: Session, selector: str | None, max_nodes: Any, seen: dict, timeout: float, opts: dict
) -> list[SnapshotNode]:
    """Whole tree within *max_nodes* (linear), else the selector's subtree (superlinear)."""
    root = await _backend_id_of(session, selector, timeout) if selector else None
    count = await _count_nodes(session, timeout) if max_nodes is not None else 0
    seen["count"] = count or "no"
    over = max_nodes is not None and count > max_nodes
    if over and root is None:
        raise _too_large(count, "The page", max_nodes)
    scope = seen["scope"] = root if over else None
    limit = float("inf") if max_nodes is None else max_nodes
    # each cross-site iframe gets what is left; over it, its line says it was left out
    bounds = _Bounds(seen["deadline"], limit - (0 if scope else count))
    tree = await fetch_tree(session, root=scope, timeout=timeout, _bounds=bounds)
    seen["sessions"] = _sessions_of(tree)
    if scope and (dom := sum(1 for n in tree.nodes if n.get("backendDOMNodeId"))) > limit:
        raise _too_large(dom, "The selected part", max_nodes)
    found = [n for n in tree.nodes if root is not None and n.get("backendDOMNodeId") == root]
    nodes = await asyncio.to_thread(build_nodes, tree, pending_ref, root=root, **opts)
    # an element Chrome ignores (body, html) still scopes; one it does not show is an error
    if root is not None and (not found or (found[0].get("ignored") and not nodes)):
        raise LookupError(
            f"The element matching {selector!r} is not in the accessibility tree"
            " (hidden, aria-hidden or not rendered)"
        )
    return nodes


async def take_snapshot_nodes(
    session: Session,
    refs: RefMap,
    *,
    interactive: bool = False,
    selector: str | None = None,
    depth: int | None = None,
    max_nodes: int | None = MAX_DOM_NODES,
    snapshot_timeout: float = FETCH_TIMEOUT,
    timeout: float = SNAPSHOT_TIMEOUT,
) -> list[SnapshotNode]:
    """Snapshot the page behind *session* as :class:`SnapshotNode` trees, refs from *refs*.

    *selector* scopes to the first match's subtree (``LookupError`` if none or not in
    the AX tree). :class:`SnapshotTooLargeError` over *max_nodes* DOM nodes (``None``:
    no limit) unless *selector* names a small part, or past *snapshot_timeout* s."""
    if depth is not None and depth < 0:
        raise ValueError(f"depth must be >= 0, got {depth}")
    try:
        for _ in range(3):
            generation = refs.generation
            opts = {"interactive": interactive, "depth": depth}
            limits = (max_nodes, snapshot_timeout)
            nodes, sessions = await _snapshot_once(session, selector, limits, timeout, **opts)
            if refs.generation == generation:
                for owner, (frame_session, document) in sessions.items():
                    refs.bind(owner, frame_session, document)
                refs.settle(nodes)
                return nodes
        raise StaleElementError("The page kept navigating while it was being snapshotted")
    finally:
        # Chrome keeps the AX tree up to date while it is on: turn it off.
        try:
            await session.send("Accessibility.disable", {}, timeout=_DISABLE_TIMEOUT)
        except Exception:  # noqa: BLE001 — housekeeping on a page that may be gone
            pass


async def take_snapshot(
    session: Session,
    refs: RefMap,
    *,
    interactive: bool = False,
    selector: str | None = None,
    depth: int | None = None,
    max_chars: int | None = None,
    max_nodes: int | None = MAX_DOM_NODES,
    snapshot_timeout: float = FETCH_TIMEOUT,
    timeout: float = SNAPSHOT_TIMEOUT,
) -> str:
    """Snapshot the page behind *session* as text (see :func:`render`)."""
    opts = {"interactive": interactive, "selector": selector, "depth": depth}
    limits = {"max_nodes": max_nodes, "snapshot_timeout": snapshot_timeout}
    nodes = await take_snapshot_nodes(session, refs, **opts, **limits, timeout=timeout)
    return render(nodes, max_chars=max_chars)

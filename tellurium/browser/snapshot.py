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

Snapshots of one document share its ``getFullAXTree`` (:func:`_full_tree`) until a
command other than a snapshot's (a click, a key, an eval) goes out after it.
"""

from __future__ import annotations

import asyncio
import functools
import weakref
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
    (loop time) to answer, *nodes* DOM nodes under ``max_nodes``; *known*: the tree
    requests in flight since it began, by session and key (:func:`_full_tree`)."""

    deadline: float | None = None
    nodes: float = float("inf")
    known: dict = field(default_factory=dict)


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


# Commands sent by the snapshots, by router (the router's last id less these counts
# the others); getFullAXTree in flight, by session then (frame id, document): (task,
# other commands when sent); the *known* of the snapshots running, by router; one
# selector lookup at a time (DOM.getDocument drops the node ids given), by session.
_OWN_COMMANDS: weakref.WeakKeyDictionary[Any, int] = weakref.WeakKeyDictionary()
_IN_FLIGHT: weakref.WeakKeyDictionary[Any, dict[tuple, tuple]] = weakref.WeakKeyDictionary()
_RUNNING: weakref.WeakKeyDictionary[Any, list[dict]] = weakref.WeakKeyDictionary()
_DOM_LOCKS: weakref.WeakKeyDictionary[Any, asyncio.Lock] = weakref.WeakKeyDictionary()


async def _send(session: Session, method: str, params: dict, timeout: float) -> dict:
    if not session.closed:  # a closed one raises before allocating: no id to count
        _OWN_COMMANDS[session.router] = _OWN_COMMANDS.get(session.router, 0) + 1
    try:
        return await session.send(method, params, timeout=timeout)
    except TimeoutError:
        raise TimeoutError(f"{method} got no answer within {timeout}s") from None


def _drop_request(requests: dict, key: tuple, task: asyncio.Task) -> None:
    if requests.get(key, (None,))[0] is task:
        del requests[key]
    task.cancelled() or task.exception()  # retrieved: an abandoned one is never logged


def _usable(entry: tuple[asyncio.Task, int] | None, others: int) -> bool:
    fresh = entry is not None and entry[1] == others  # nothing else was sent since
    return fresh and not (entry[0].done() and (entry[0].cancelled() or entry[0].exception()))


async def _full_tree(
    session: Session, frame_id: str | None, document: Any, timeout: float, known: dict
) -> dict:
    """``getFullAXTree`` of *document* (``None``: not shared): the request in flight
    for it, or in flight since the snapshot began (*known*: one abandoned past its
    snapshot_timeout too), if nothing but snapshots was sent since it went out (a
    click, a key, an eval may have changed the page); else a new one."""
    params = {"frameId": frame_id} if frame_id else {}
    if document is None:
        return await _send(session, "Accessibility.getFullAXTree", params, timeout)
    requests, key = _IN_FLIGHT.setdefault(session, {}), (frame_id or "", document)
    others = session.router._next_msg_id - _OWN_COMMANDS.get(session.router, 0)
    entry = next(
        (e for e in (requests.get(key), known.get((session, key))) if _usable(e, others)), None
    )
    if entry is None:
        request = _send(session, "Accessibility.getFullAXTree", params, timeout)
        task = asyncio.ensure_future(request)
        entry = requests[key] = (task, others)  # the task has not sent it yet
        for running in _RUNNING.get(session.router, ()):
            running[(session, key)] = entry
        task.add_done_callback(functools.partial(_drop_request, requests, key))
    return await asyncio.wait_for(asyncio.shield(entry[0]), timeout)


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
    order, whichever renderer answers first: each waits for those before it."""

    def __init__(self, bounds: _Bounds, size: int) -> None:
        self._bounds, self._counts, self._next = bounds, {}, 0
        self._verdicts = [asyncio.get_running_loop().create_future() for _ in range(size)]

    def report(self, index: int, count: int | None) -> None:
        """The *index*-th iframe has *count* DOM nodes (``None``: takes none); first wins."""
        self._counts.setdefault(index, count)
        while self._next in self._counts:
            nodes = self._counts[self._next]
            fits = nodes is not None and nodes <= self._bounds.nodes
            if fits:
                self._bounds.nodes -= nodes
            self._verdicts[self._next].set_result(fits)
            self._next += 1

    async def admit(self, index: int, count: int) -> bool:  # fits what those before leave?
        self.report(index, count)
        return await asyncio.shield(self._verdicts[index])


async def _oopif_tree(
    session: Session, frame_id: str, sub: dict, slot: tuple[_Ledger | None, int], within: float
) -> AXTree:
    """The tree of the cross-site iframe *frame_id*, with its document's loader id; with
    a ledger in *slot*, counted first within *within* s (a stuck one holds no other)."""
    ledger, index = slot
    timeout = sub["timeout"]

    async def counted() -> tuple[Session, int]:
        child = await _oopif_session(session, frame_id, timeout)
        return child, await _count_nodes(child, timeout) if ledger else 0

    child, count = await asyncio.wait_for(counted(), within if ledger else None)
    if ledger and not await ledger.admit(index, count):
        raise _TooLarge(count)
    loaded = await _send(child, "Page.getFrameTree", {}, timeout)
    document = str(loaded["frameTree"]["frame"].get("loaderId") or "")
    tree = await fetch_tree(child, **sub, _owner=child.session_id or "", _document=document or None)
    tree.document = document
    return tree


async def _frame_of(
    session: Session, bid: int, base_url: str, owner: str, sub: dict, slot: tuple
) -> AXTree | str | None:
    """The document of the ``<iframe>`` with backend id *bid*: tree, OOPIF URL or ``None``.
    *sub* holds the :func:`fetch_tree` options of the frame; an OOPIF has until the
    deadline of its ``_bounds`` to answer, its nested frames included; *slot*: (ledger
    of its document or ``None`` without a node budget, its place)."""
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
    if "contentDocument" in node and slot[0]:  # same renderer: no budget of its own
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
        document = node["contentDocument"].get("backendNodeId")
        return await fetch_tree(session, frame_id=frame_id, **sub, _owner=owner, _document=document)
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
    _document: Any = None,
) -> AXTree:
    """Fetch the AX tree of a document (the main frame by default) and its iframes,
    cross-site ones too; with *root* (a backend node id) only that node's subtree
    (``queryAXTree``). The whole tree of a *_document* (its identity) is shared
    with the snapshots asking for it at the same time (:func:`_full_tree`)."""
    if root is not None:
        query = {"backendNodeId": root}
        result = await _send(session, "Accessibility.queryAXTree", query, timeout)
    else:
        known = _bounds.known if _bounds else {}
        result = await _full_tree(session, frame_id, _document, timeout, known)
    nodes = result.get("nodes", [])
    frames = [n for n in nodes if _role(n) == "Iframe" and not n.get("ignored")]
    iframes = [bid for n in frames if (bid := n.get("backendDOMNodeId"))]
    tree, base_url = AXTree(nodes=nodes, owner=_owner, session=session), _document_url(nodes)
    if iframes:
        sub = {"timeout": timeout, "_nesting": _nesting + 1, "_bounds": _bounds}
        limited = _bounds is not None and _bounds.nodes != float("inf")
        ledger = _Ledger(_bounds, len(iframes)) if limited else None
        tasks = [
            asyncio.ensure_future(_frame_of(session, b, base_url, _owner, sub, (ledger, i)))
            for i, b in enumerate(iframes)
        ]
        for i, task in enumerate(tasks):  # one not read across sites holds no other
            task.add_done_callback(lambda _, i=i: ledger and ledger.report(i, None))
        subs = await asyncio.gather(*tasks)
        tree.frames = {bid: f for bid, f in zip(iframes, subs, strict=True) if f is not None}
    return tree


async def _backend_id_of(session: Session, document: int, selector: str, timeout: float) -> int:
    query = {"nodeId": document, "selector": selector}
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
    known = {(s, k): e for s, r in list(_IN_FLIGHT.items()) for k, e in r.items()}
    seen = {"count": "no", "scope": None, "sessions": {}, "deadline": deadline, "known": known}
    (running := _RUNNING.setdefault(session.router, [])).append(known)
    steps = _steps(session, selector, limits[0], seen, timeout, opts)
    try:
        return await asyncio.wait_for(steps, limits[1]), seen["sessions"]
    except TimeoutError:
        hint = "a narrower selector= or " if seen["scope"] else ""
        raise SnapshotTooLargeError(
            f"The snapshot took over snapshot_timeout={limits[1]:g} s ({seen['count']} DOM nodes"
            f" counted; shadow DOM is not): pass {hint}a higher snapshot_timeout="
        ) from None
    finally:
        running[:] = [k for k in running if k is not known]  # by identity: dicts compare equal


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
    async with _DOM_LOCKS.setdefault(session, asyncio.Lock()):
        doc = (await _send(session, "DOM.getDocument", {"depth": 0}, timeout))["root"]
        root = await _backend_id_of(session, doc["nodeId"], selector, timeout) if selector else None
        count = await _count_nodes(session, timeout) if max_nodes is not None else 0
    seen["count"] = count or "no"
    over = max_nodes is not None and count > max_nodes
    if over and root is None:
        raise _too_large(count, "The page", max_nodes)
    scope = seen["scope"] = root if over else None
    limit = float("inf") if max_nodes is None else max_nodes
    # each cross-site iframe gets what is left; over it, its line says it was left out
    bounds = _Bounds(seen["deadline"], limit - (0 if scope else count), seen["known"])
    opened = {"_bounds": bounds, "_document": doc.get("backendNodeId")}
    tree = await fetch_tree(session, root=scope, timeout=timeout, **opened)
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
            await _send(session, "Accessibility.disable", {}, _DISABLE_TIMEOUT)
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

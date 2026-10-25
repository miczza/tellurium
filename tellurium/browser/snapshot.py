"""Accessibility snapshot of a page, compact enough for an LLM.

``Accessibility.getFullAXTree`` (or ``queryAXTree`` for a ``selector=``) gives
the AX nodes; pure functions prune them into :class:`SnapshotNode` trees, which
:mod:`~tellurium.browser.snapshot_text` renders as lines. Same-process iframes are
stitched under their ``iframe`` node, and so are cross-site ones (OOPIFs), read
through their own session; an OOPIF that cannot be reached shows as
``- iframe "<url>" [oopif]``. Refs come from the tab's
:class:`~tellurium.browser.refs.RefMap`. No ``Runtime.enable``: only the
Accessibility, DOM and Target domains.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from tellurium.browser import geometry
from tellurium.browser.handles import StaleElementError
from tellurium.browser.refs import pending_ref
from tellurium.browser.snapshot_text import is_text, render, squash
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
# Wait for a cross-site iframe that auto-attach is attaching, before attaching it.
_AUTO_ATTACH_WAIT = 1.0
_DISABLE_TIMEOUT = 0.2  # sent either way: only the wait for the answer is cut
# AX nesting walked at most, across stitched iframes too: two Python frames per
# level keep the recursion far from the interpreter's limit (1000).
_MAX_AX_NESTING = 250

# Never shown, nor their subtrees.
_DROPPED = frozenset({"InlineTextBox", "ListMarker", "LineBreak"})
# Containers that only group: their children take their place when nameless.
_TRANSPARENT = frozenset({"generic", "none", "presentation", "LabelText", "MenuListPopup"})
# Their content is their value or name: children are not walked.
_LEAVES = frozenset("textbox searchbox spinbutton slider checkbox radio switch image img".split())
# What an agent can act on (``interactive=True``).
_INTERACTIVE = frozenset(
    "button link textbox searchbox checkbox radio switch combobox listbox option menuitem"
    " menuitemcheckbox menuitemradio slider spinbutton tab treeitem DisclosureTriangle".split()
)


class SnapshotTooLargeError(RuntimeError):
    """The page is over the snapshot size limit: snapshot a part with ``selector=``."""


@dataclass
class SnapshotNode:
    """One node of a snapshot. *ref* is ``None`` for text (``role == "text"``) and
    for an OOPIF placeholder (``states == {"oopif": True}``, URL in *name*);
    *states* may hold checked, pressed, expanded, disabled, selected, level."""

    ref: str | None
    role: str
    name: str
    value: str | None = None
    states: dict[str, bool | int | str] = field(default_factory=dict)
    children: list[SnapshotNode] = field(default_factory=list)


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
    except asyncio.TimeoutError:
        raise TimeoutError(f"{method} got no answer within {timeout}s") from None


def _role(node: dict[str, Any]) -> str:
    return (node.get("role") or {}).get("value") or ""


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


async def _frame_of(
    session: Session, bid: int, base_url: str, nesting: int, timeout: float, owner: str
) -> AXTree | str | None:
    """The document of the ``<iframe>`` with backend id *bid*: tree, OOPIF URL or ``None``."""
    try:
        described = await _send(session, "DOM.describeNode", {"backendNodeId": bid}, timeout)
    except CDPError:  # detached meanwhile
        return None
    node = described.get("node", {})
    if not (frame_id := node.get("frameId")):
        return None
    if nesting >= _MAX_FRAME_NESTING:  # too deep: shown without content
        return None
    sub = {"timeout": timeout, "_nesting": nesting + 1}
    if "contentDocument" not in node:  # the document lives in another renderer
        try:
            child = await _oopif_session(session, frame_id, timeout)
            loaded = await _send(child, "Page.getFrameTree", {}, timeout)
            tree = await fetch_tree(child, **sub, _owner=child.session_id or "")
            tree.document = str(loaded["frameTree"]["frame"].get("loaderId") or "")
            return tree
        except (CDPError, ConnectionError, TimeoutError, KeyError):
            attributes = node.get("attributes", [])
            src = dict(zip(attributes[::2], attributes[1::2], strict=False)).get("src", "")
            return urljoin(base_url, src) if src else "about:blank"
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
        subs = await asyncio.gather(
            *(_frame_of(session, b, base_url, _nesting, timeout, _owner) for b in iframes)
        )
        tree.frames = {bid: sub for bid, sub in zip(iframes, subs, strict=True) if sub is not None}
    return tree


def _props(node: dict[str, Any]) -> dict[str, Any]:
    return {p.get("name"): (p.get("value") or {}).get("value") for p in node.get("properties", [])}


def _states(props: dict[str, Any], role: str) -> dict[str, bool | int | str]:
    states: dict[str, bool | int | str] = {
        key: "mixed" if props[key] == "mixed" else props[key] in (True, "true")
        for key in ("checked", "pressed")
        if key in props
    }
    if "expanded" in props:
        states["expanded"] = bool(props["expanded"])
    states.update({key: True for key in ("disabled", "selected") if props.get(key) is True})
    # a level says something on headings and tree items; on list items it is noise
    if role in ("heading", "treeitem") and isinstance(props.get("level"), int):
        states["level"] = props["level"]
    return states


class _Pruner:
    """Walks one document's AX nodes; a sub-pruner walks each stitched iframe."""

    def __init__(self, tree: AXTree, ref_for: Callable[..., str], interactive: bool, depth):
        self.tree, self.ref_for, self.interactive, self.depth = tree, ref_for, interactive, depth
        self.by_id = {node["nodeId"]: node for node in tree.nodes}
        roots = (n.get("frameId") for n in tree.nodes if _role(n) == "RootWebArea")
        self.frame = next(roots, None) or ""  # the document's frame, for the refs

    def walk(self, root: int | None, level: int, nesting: int) -> list[SnapshotNode]:
        """From *root* (a backend node id), else from the document node."""
        if root is not None:
            tops = [n for n in self.tree.nodes if n.get("backendDOMNodeId") == root][:1]
        else:
            tops = [n for n in self.tree.nodes if not n.get("parentId")][:1]
        return [snap for top in tops for snap in self.emit(top, level, nesting)]

    def children(self, node: dict[str, Any], level: int, nesting: int) -> list[SnapshotNode]:
        out: list[SnapshotNode] = []
        if nesting >= _MAX_AX_NESTING:
            return out
        for child_id in node.get("childIds", []):
            child = self.by_id.get(child_id)
            if child is not None:
                out += self.emit(child, level, nesting + 1)
        return out

    def emit(self, node: dict[str, Any], level: int, nesting: int = 0) -> list[SnapshotNode]:
        """The snapshot nodes standing for *node* placed at *level*."""
        role = _role(node)
        name = squash((node.get("name") or {}).get("value") or "")
        if role in _DROPPED:
            return []
        if node.get("ignored") or role == "RootWebArea" or (role in _TRANSPARENT and not name):
            return self.children(node, level, nesting)
        if level >= self.depth:
            return []
        if role == "StaticText":
            # raw: adjacent pieces are fused before spaces are collapsed
            raw = str((node.get("name") or {}).get("value") or "")
            return [] if self.interactive else [SnapshotNode(None, "text", raw)]
        if role == "Iframe":
            return self.iframe(node, name, level, nesting + 1)
        props = _props(node)
        if self.interactive and not (
            role in _INTERACTIVE or (props.get("editable") and props.get("focusable"))
        ):
            return self.children(node, level, nesting)
        value = (node.get("value") or {}).get("value")
        snap = SnapshotNode(
            ref=self.ref_for(bid, self.frame, self.tree.owner)
            if (bid := node.get("backendDOMNodeId"))
            else None,
            role=role,
            name=name,
            value=None if value in (None, "") else str(value),
            states=_states(props, role),
        )
        if role not in _LEAVES:
            snap.children = _fuse(self.children(node, level + 1, nesting), name, snap.value)
        return [snap]

    def iframe(
        self, node: dict[str, Any], name: str, level: int, nesting: int
    ) -> list[SnapshotNode]:
        # *nesting* carries on into the frame: the limit is for the whole walk
        frame = self.tree.frames.get(node.get("backendDOMNodeId") or 0)
        if isinstance(frame, str):
            return [SnapshotNode(None, "iframe", frame, states={"oopif": True})]
        inner = _Pruner(frame, self.ref_for, self.interactive, self.depth) if frame else None
        if self.interactive:
            return inner.walk(None, level, nesting) if inner else []
        snap = SnapshotNode(
            self.ref_for(node["backendDOMNodeId"], self.frame, self.tree.owner), "iframe", name
        )
        snap.children = inner.walk(None, level + 1, nesting) if inner else []
        return [snap]


def _fuse(children: list[SnapshotNode], name: str, value: str | None) -> list[SnapshotNode]:
    """Fuse adjacent text, collapse its spaces, drop text repeating a name (a label
    next to its control, the content of a named node)."""
    fused: list[SnapshotNode] = []
    for child in children:
        if is_text(child) and fused and is_text(fused[-1]):
            fused[-1].name += " " + child.name
        else:
            fused.append(child)
    for child in fused:
        if is_text(child):
            child.name = squash(child.name)
    out = []
    for i, child in enumerate(fused):
        if is_text(child):
            near = [s.name for s in fused[max(i - 1, 0) : i + 2] if not is_text(s)]
            if not child.name or child.name in near:
                continue
        out.append(child)
    if out and all(is_text(c) for c in out) and " ".join(c.name for c in out) in (name, value):
        return []
    return out


def build_nodes(
    tree: AXTree,
    ref_for: Callable[[int, str, str], str],
    *,
    interactive: bool = False,
    root: int | None = None,
    depth: int | None = None,
) -> list[SnapshotNode]:
    """Prune *tree* into snapshot nodes, naming each ``ref_for(backend_id, frame_id, owner)``.

    *interactive* keeps only what an agent can act on; *root* (a backend node
    id) scopes to that node's subtree; *depth* keeps that many levels (text
    included), ``0`` gives nothing.
    """
    if depth is not None and depth < 0:
        raise ValueError(f"depth must be >= 0, got {depth}")
    pruner = _Pruner(tree, ref_for, interactive, float("inf") if depth is None else depth)
    return _fuse(pruner.walk(root, 0, 0), "", None)


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
    seen: dict[str, Any] = {"count": "no", "scope": None, "sessions": {}}
    steps = _steps(session, selector, limits[0], seen, timeout, opts)
    try:
        return await asyncio.wait_for(steps, limits[1]), seen["sessions"]
    except asyncio.TimeoutError:
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
    tree = await fetch_tree(session, root=scope, timeout=timeout)
    seen["sessions"] = _sessions_of(tree)
    if scope and (dom := sum(1 for n in tree.nodes if n.get("backendDOMNodeId"))) > max_nodes:
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

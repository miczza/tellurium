"""Accessibility snapshot of a page, compact enough for an LLM.

``Accessibility.getFullAXTree`` (or ``queryAXTree`` for a ``selector=``) gives
the AX nodes; pure functions prune them and render lines such as
``- textbox "Email" [ref=e5]: "ada@example.com"``. Same-process iframes are
stitched under their ``iframe`` node, an OOPIF shows as ``- iframe "<url>"
[oopif]``. Refs come from the tab's :class:`~tellurium.browser.refs.RefMap`.
No ``Runtime.enable``: only the Accessibility, DOM and Memory domains.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from tellurium.browser.handles import StaleElementError
from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.refs import RefMap
    from tellurium.cdp.transport._session import Session

# Bound of each CDP command of a snapshot; a 5000-node tree answers in ~0.1 s.
SNAPSHOT_TIMEOUT = 30.0
# Bigger pages are refused (pass ``selector=``): Chrome needs ~1 s and ~50 MB
# of JSON for 50000 nodes, parsed on the event loop by the transport.
MAX_DOM_NODES = 50_000
MAX_AX_NODES = 120_000
# Iframes nested deeper than this are shown without their content.
_MAX_FRAME_NESTING = 8
_DISABLE_TIMEOUT = 2.0
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
_SPACES = re.compile(r"\s+")
# Page text longer than this is cut in the rendering, with a ``[+N chars]`` signal.
_MAX_TEXT = 300
# Left raw by json.dumps: C1 controls, bidi marks/overrides/isolates, separators.
_UNSAFE = re.compile("[\x7f-\x9f\u061c\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff]")


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
    to its document's tree (same process) or its URL (OOPIF, not fetched)."""

    nodes: list[dict[str, Any]]
    frames: dict[int, AXTree | str] = field(default_factory=dict)

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
    for node in nodes:
        if _role(node) == "RootWebArea":
            for prop in node.get("properties", []):
                if prop.get("name") == "url":
                    return str(prop.get("value", {}).get("value") or "")
    return ""


async def _frame_of(
    session: Session, backend_node_id: int, base_url: str, nesting: int, timeout: float
) -> AXTree | str | None:
    """The document of the ``<iframe>`` *backend_node_id*: tree, OOPIF URL or ``None``."""
    try:
        described = await _send(
            session, "DOM.describeNode", {"backendNodeId": backend_node_id}, timeout
        )
    except CDPError:  # detached meanwhile
        return None
    node = described.get("node", {})
    frame_id = node.get("frameId")
    if not frame_id:
        return None
    if "contentDocument" not in node:  # the document lives in another renderer
        attributes = node.get("attributes", [])
        src = dict(zip(attributes[::2], attributes[1::2], strict=False)).get("src", "")
        return urljoin(base_url, src) if src else "about:blank"
    if nesting >= _MAX_FRAME_NESTING:
        return None
    try:
        return await fetch_tree(session, frame_id=frame_id, timeout=timeout, _nesting=nesting + 1)
    except CDPError:  # the frame went away between the two calls
        return None


async def fetch_tree(
    session: Session,
    *,
    frame_id: str | None = None,
    root: int | None = None,
    timeout: float = SNAPSHOT_TIMEOUT,
    _nesting: int = 0,
) -> AXTree:
    """Fetch the AX tree of a document (the main frame by default) and its iframes.

    With *root* (a backend node id) only that node's subtree is fetched
    (``Accessibility.queryAXTree``), at a cost proportional to the subtree.
    """
    if root is not None:
        method, params = "Accessibility.queryAXTree", {"backendNodeId": root}
    else:
        method, params = "Accessibility.getFullAXTree", {"frameId": frame_id} if frame_id else {}
    result = await _send(session, method, params, timeout)
    nodes = result.get("nodes", [])
    iframes = [
        node["backendDOMNodeId"]
        for node in nodes
        if _role(node) == "Iframe" and not node.get("ignored") and node.get("backendDOMNodeId")
    ]
    tree = AXTree(nodes=nodes)
    if iframes:
        base_url = _document_url(nodes)
        subs = await asyncio.gather(
            *(_frame_of(session, bid, base_url, _nesting, timeout) for bid in iframes)
        )
        tree.frames = {bid: sub for bid, sub in zip(iframes, subs, strict=True) if sub is not None}
    return tree


def _text(value: Any) -> str:
    return _SPACES.sub(" ", str(value)).strip()


def _props(node: dict[str, Any]) -> dict[str, Any]:
    return {p.get("name"): (p.get("value") or {}).get("value") for p in node.get("properties", [])}


def _states(props: dict[str, Any], role: str) -> dict[str, bool | int | str]:
    states: dict[str, bool | int | str] = {}
    for key in ("checked", "pressed"):
        if key in props:
            value = props[key]
            states[key] = "mixed" if value == "mixed" else value in (True, "true")
    if "expanded" in props:
        states["expanded"] = bool(props["expanded"])
    states.update({key: True for key in ("disabled", "selected") if props.get(key) is True})
    # a level says something on headings and tree items; on list items it is noise
    if role in ("heading", "treeitem") and isinstance(props.get("level"), int):
        states["level"] = props["level"]
    return states


class _Pruner:
    """Walks one document's AX nodes; a sub-pruner walks each stitched iframe."""

    def __init__(self, tree: AXTree, ref_for: Callable[[int], str], interactive: bool, depth):
        self.tree, self.ref_for, self.interactive, self.depth = tree, ref_for, interactive, depth
        self.by_id = {node["nodeId"]: node for node in tree.nodes}

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
        name = _text((node.get("name") or {}).get("value") or "")
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
            ref=self.ref_for(node["backendDOMNodeId"]) if node.get("backendDOMNodeId") else None,
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
        snap = SnapshotNode(self.ref_for(node["backendDOMNodeId"]), "iframe", name)
        snap.children = inner.walk(None, level + 1, nesting) if inner else []
        return [snap]


def _is_text(node: SnapshotNode) -> bool:
    return node.role == "text" and node.ref is None


def _fuse(children: list[SnapshotNode], name: str, value: str | None) -> list[SnapshotNode]:
    """Fuse adjacent text, collapse its spaces, drop text repeating a name (a label
    next to its control, the content of a named node)."""
    fused: list[SnapshotNode] = []
    for child in children:
        if _is_text(child) and fused and _is_text(fused[-1]):
            fused[-1].name += " " + child.name
        else:
            fused.append(child)
    for child in fused:
        if _is_text(child):
            child.name = _text(child.name)
    out = []
    for i, child in enumerate(fused):
        if _is_text(child):
            near = [s.name for s in fused[max(i - 1, 0) : i + 2] if not _is_text(s)]
            if not child.name or child.name in near:
                continue
        out.append(child)
    if out and all(_is_text(c) for c in out) and " ".join(c.name for c in out) in (name, value):
        return []
    return out


def build_nodes(
    tree: AXTree,
    ref_for: Callable[[int], str],
    *,
    interactive: bool = False,
    root: int | None = None,
    depth: int | None = None,
) -> list[SnapshotNode]:
    """Prune *tree* into snapshot nodes, naming each with ``ref_for(backend_id)``.

    *interactive* keeps only what an agent can act on; *root* (a backend node
    id) scopes to that node's subtree; *depth* keeps that many levels (text
    included), ``0`` gives nothing.
    """
    if depth is not None and depth < 0:
        raise ValueError(f"depth must be >= 0, got {depth}")
    pruner = _Pruner(tree, ref_for, interactive, float("inf") if depth is None else depth)
    return _fuse(pruner.walk(root, 0, 0), "", None)


def _quote(text: str) -> str:
    """Page text as a JSON string with control and bidi characters escaped, capped:
    nothing a page writes can end the quotes, break the line or fake a ref."""
    extra = len(text) - _MAX_TEXT
    quoted = json.dumps(text[:_MAX_TEXT] + "…" if extra > 0 else text, ensure_ascii=False)
    quoted = _UNSAFE.sub(lambda m: f"\\u{ord(m.group()):04x}", quoted)
    return f"{quoted} [+{extra} chars]" if extra > 0 else quoted


def _head(node: SnapshotNode) -> str:
    parts = [node.role]
    if node.name:
        parts.append(_quote(node.name))
    for key, state in node.states.items():
        if key == "oopif":
            parts.append("[oopif]")
        elif key == "level":
            parts.append(f"[level={state}]")
        elif state is True:
            parts.append(f"[{key}]")
        elif key == "expanded" or state == "mixed":
            parts.append(f"[{key}={str(state).lower()}]")
    if node.ref:
        parts.append(f"[ref={node.ref}]")
    return " ".join(parts)


def _lines(nodes: list[SnapshotNode], indent: str, out: list[str]) -> None:
    for node in nodes:
        if _is_text(node):
            out.append(f"{indent}- text: {_quote(node.name)}")
            continue
        line, children = f"{indent}- {_head(node)}", node.children
        if node.value is not None:
            line += f": {_quote(_text(node.value))}"
        elif len(children) == 1 and _is_text(children[0]):
            line, children = f"{line}: {_quote(children[0].name)}", []
        elif children:
            line += ":"
        out.append(line)
        _lines(children, indent + "  ", out)


def render(nodes: list[SnapshotNode], *, max_chars: int | None = None) -> str:
    """Render *nodes* as ``- role "name" [state] [ref=eN]: "value"`` lines.

    With *max_chars*, whole lines are kept while they fit and a last line
    ``- [truncated: N more lines; ...]`` says what was cut; the result never
    exceeds *max_chars* (shorter signals when it is tiny).
    """
    if max_chars is not None and max_chars < 1:
        raise ValueError(f"max_chars must be >= 1, got {max_chars}")
    lines: list[str] = []
    _lines(nodes, "", lines)
    text = "\n".join(lines)
    if max_chars is None or len(text) <= max_chars:
        return text
    sizes = [0]
    for line in lines:
        sizes.append(sizes[-1] + len(line) + 1)
    for marker in (
        "- [truncated: {} more lines; narrow with selector=, depth= or interactive=True]",
        "- [truncated: {} more lines]",
        "- [truncated]",
    ):
        for kept in range(len(lines) - 1, -1, -1):
            signal = marker.format(len(lines) - kept)
            if sizes[kept] + len(signal) <= max_chars:
                return "\n".join([*lines[:kept], signal])
    return "…"


async def _backend_id_of(session: Session, selector: str, timeout: float) -> int:
    doc = await _send(session, "DOM.getDocument", {"depth": 0}, timeout)
    query = {"nodeId": doc["root"]["nodeId"], "selector": selector}
    node_id = (await _send(session, "DOM.querySelector", query, timeout)).get("nodeId", 0)
    if not node_id:
        raise LookupError(f"No element matching {selector!r}")
    described = await _send(session, "DOM.describeNode", {"nodeId": node_id}, timeout)
    return described["node"]["backendNodeId"]


async def _check_size(session: Session, timeout: float) -> None:
    try:
        counters = await _send(session, "Memory.getDOMCounters", {}, timeout)
    except CDPError:  # not available: the AX node count still bounds the work
        return
    if counters.get("nodes", 0) > MAX_DOM_NODES:
        raise SnapshotTooLargeError(
            f"The page has {counters['nodes']} DOM nodes, over the snapshot limit of"
            f" {MAX_DOM_NODES}: pass selector= to snapshot a part of it"
        )


def _pending_ref(backend_node_id: int) -> str:
    return f"#{backend_node_id}"


def _assign_refs(nodes: list[SnapshotNode], refs: RefMap) -> None:
    """Swap the pending refs of an off-loop build for real ones, in document order."""
    for node in nodes:
        if node.ref and node.ref.startswith("#"):
            node.ref = refs.ref_for(int(node.ref[1:]))
        _assign_refs(node.children, refs)


async def _snapshot_once(
    session: Session, selector: str | None, timeout: float, **options: Any
) -> list[SnapshotNode]:
    root = await _backend_id_of(session, selector, timeout) if selector else None
    if root is None:
        await _check_size(session, timeout)
    tree = await fetch_tree(session, root=root, timeout=timeout)
    if len(tree.nodes) > MAX_AX_NODES:
        raise SnapshotTooLargeError(
            f"{len(tree.nodes)} accessibility nodes, over the snapshot limit of"
            f" {MAX_AX_NODES}: pass a narrower selector="
        )
    if root is not None and not any(
        n.get("backendDOMNodeId") == root and not n.get("ignored") for n in tree.nodes
    ):
        raise LookupError(
            f"The element matching {selector!r} is not in the accessibility tree"
            " (hidden, aria-hidden or not rendered)"
        )
    # pruning a big tree takes tens of ms: off the event loop
    return await asyncio.to_thread(build_nodes, tree, _pending_ref, root=root, **options)


async def take_snapshot_nodes(
    session: Session,
    refs: RefMap,
    *,
    interactive: bool = False,
    selector: str | None = None,
    depth: int | None = None,
    timeout: float = SNAPSHOT_TIMEOUT,
) -> list[SnapshotNode]:
    """Snapshot the page behind *session* as :class:`SnapshotNode` trees, refs from *refs*.

    *selector* scopes to the first match's subtree (``LookupError`` if none or not
    in the AX tree). Over :data:`MAX_DOM_NODES`, without *selector*, raises
    :class:`SnapshotTooLargeError`. A tree fetched during a main-frame navigation
    is fetched again, so refs always name the current document.
    """
    if depth is not None and depth < 0:
        raise ValueError(f"depth must be >= 0, got {depth}")
    try:
        for _ in range(3):
            generation = refs.generation
            nodes = await _snapshot_once(
                session, selector, timeout, interactive=interactive, depth=depth
            )
            if refs.generation == generation:
                _assign_refs(nodes, refs)
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
    timeout: float = SNAPSHOT_TIMEOUT,
) -> str:
    """Snapshot the page behind *session* as text (see :func:`render`)."""
    nodes = await take_snapshot_nodes(
        session, refs, interactive=interactive, selector=selector, depth=depth, timeout=timeout
    )
    return render(nodes, max_chars=max_chars)

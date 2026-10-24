"""Accessibility snapshot of a page, compact enough for an LLM.

``Accessibility.getFullAXTree`` gives every AX node of a document; pure
functions then prune it (ignored nodes, nameless containers, inline text
boxes), fuse static text, keep value and state, and render it as text::

    - heading "Sign in" [level=1] [ref=e2]
    - textbox "Email" [ref=e5]: ada@example.com
    - checkbox "Remember me" [checked] [ref=e6]

Same-process iframes are fetched per frame and stitched under their
``iframe`` node; an out-of-process iframe shows as ``- iframe "<url>" [oopif]``.
Each shown node gets a ref from the tab's :class:`~tellurium.browser.refs.RefMap`.
No ``Runtime.enable``: only the Accessibility and DOM domains are used.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.cdp.transport._session import Session

# Bound of each CDP command of a snapshot; a 5000-node tree answers in ~0.1 s.
SNAPSHOT_TIMEOUT = 30.0
# Iframes nested deeper than this are shown without their content.
_MAX_FRAME_NESTING = 8
# AX nesting walked at most (keeps the recursion far from Python's limit).
_MAX_AX_NESTING = 300

# Never shown, nor their subtrees.
_DROPPED = frozenset({"InlineTextBox", "ListMarker", "LineBreak"})
# Containers that only group: their children take their place when nameless.
_TRANSPARENT = frozenset({"generic", "none", "presentation", "LabelText", "MenuListPopup"})
# Their content is their value or name: children are not walked.
_LEAVES = frozenset(
    {"textbox", "searchbox", "spinbutton", "slider", "checkbox", "radio", "switch", "image", "img"}
)
# What an agent can act on (``interactive=True``).
_INTERACTIVE = frozenset(
    {
        "button",
        "link",
        "textbox",
        "searchbox",
        "checkbox",
        "radio",
        "switch",
        "combobox",
        "listbox",
        "option",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "slider",
        "spinbutton",
        "tab",
        "treeitem",
        "DisclosureTriangle",
    }
)
_SPACES = re.compile(r"\s+")


@dataclass
class SnapshotNode:
    """One node of a snapshot.

    *ref* is ``None`` for text (``role == "text"``, the text in *name*) and for
    an out-of-process iframe placeholder (``states == {"oopif": True}``, the
    frame URL in *name*). *states* holds ``checked`` (``True``/``False``/
    ``"mixed"``), ``pressed``, ``expanded``, ``disabled``, ``selected`` and
    ``level`` when the node has them.
    """

    ref: str | None
    role: str
    name: str
    value: str | None = None
    states: dict[str, bool | int | str] = field(default_factory=dict)
    children: list[SnapshotNode] = field(default_factory=list)


@dataclass
class AXTree:
    """The raw AX nodes of one document, plus the documents of its iframes.

    *frames* maps an ``<iframe>``'s backend node id to its document's tree
    (same process) or to its URL (out-of-process iframe, content not fetched).
    """

    nodes: list[dict[str, Any]]
    frames: dict[int, AXTree | str] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AXTree:
        frames: dict[int, AXTree | str] = {}
        for key, sub in data.get("frames", {}).items():
            frames[int(key)] = sub if isinstance(sub, str) else cls.from_json(sub)
        return cls(nodes=data["nodes"], frames=frames)

    def to_json(self) -> dict[str, Any]:
        frames = {
            str(key): sub if isinstance(sub, str) else sub.to_json()
            for key, sub in self.frames.items()
        }
        return {"nodes": self.nodes, "frames": frames}


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
    timeout: float = SNAPSHOT_TIMEOUT,
    _nesting: int = 0,
) -> AXTree:
    """Fetch the AX tree of a document (the main frame by default) and its iframes."""
    params = {"frameId": frame_id} if frame_id else {}
    result = await _send(session, "Accessibility.getFullAXTree", params, timeout)
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


# ---------------------------------------------------------------------------
# Pruning: AX nodes -> SnapshotNode (pure)


def _text(value: Any) -> str:
    return _SPACES.sub(" ", str(value)).strip()


def _props(node: dict[str, Any]) -> dict[str, Any]:
    return {p.get("name"): (p.get("value") or {}).get("value") for p in node.get("properties", [])}


def _tristate(value: Any) -> bool | str:
    return "mixed" if value == "mixed" else value in (True, "true")


def _states(props: dict[str, Any]) -> dict[str, bool | int | str]:
    states: dict[str, bool | int | str] = {}
    for key in ("checked", "pressed"):
        if key in props:
            states[key] = _tristate(props[key])
    if "expanded" in props:
        states["expanded"] = bool(props["expanded"])
    for key in ("disabled", "selected"):
        if props.get(key) is True:
            states[key] = True
    if isinstance(props.get("level"), int) and props["level"] > 0:
        states["level"] = props["level"]
    return states


class _Pruner:
    """Walks one document's AX nodes; a sub-pruner walks each stitched iframe."""

    def __init__(
        self,
        tree: AXTree,
        ref_for: Callable[[int], str],
        interactive: bool,
        depth: float,
    ) -> None:
        self.tree = tree
        self.by_id = {node["nodeId"]: node for node in tree.nodes}
        self.ref_for = ref_for
        self.interactive = interactive
        self.depth = depth

    def roots(self, root: int | None) -> list[dict[str, Any]]:
        if root is not None:
            return [n for n in self.tree.nodes if n.get("backendDOMNodeId") == root][:1]
        return [n for n in self.tree.nodes if not n.get("parentId")][:1]

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
            return self.iframe(node, name, level)
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
            states=_states(props),
        )
        if role not in _LEAVES:
            snap.children = _fuse(self.children(node, level + 1, nesting), name, snap.value)
        return [snap]

    def iframe(self, node: dict[str, Any], name: str, level: int) -> list[SnapshotNode]:
        frame = self.tree.frames.get(node.get("backendDOMNodeId") or 0)
        if isinstance(frame, str):
            return [SnapshotNode(None, "iframe", frame, states={"oopif": True})]
        inner = _Pruner(frame, self.ref_for, self.interactive, self.depth) if frame else None
        if self.interactive:
            return [n for r in inner.roots(None) for n in inner.emit(r, level)] if inner else []
        snap = SnapshotNode(self.ref_for(node["backendDOMNodeId"]), "iframe", name)
        if inner:
            snap.children = [n for r in inner.roots(None) for n in inner.emit(r, level + 1)]
        return [snap]


def _fuse(children: list[SnapshotNode], name: str, value: str | None) -> list[SnapshotNode]:
    """Fuse adjacent text, collapse its spaces, drop text that repeats the name."""
    fused: list[SnapshotNode] = []
    for child in children:
        if child.role == "text" and child.ref is None and fused and fused[-1].role == "text":
            fused[-1].name += " " + child.name
        else:
            fused.append(child)
    out = []
    for child in fused:
        if child.role == "text" and child.ref is None:
            child.name = _text(child.name)
            if not child.name:
                continue
        out.append(child)
    if out and all(c.role == "text" for c in out):
        joined = " ".join(c.name for c in out)
        if joined in (name, value):
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
    nodes = [n for r in pruner.roots(root) for n in pruner.emit(r, 0)]
    return _fuse(nodes, "", None)


# ---------------------------------------------------------------------------
# Rendering (pure)


def _head(node: SnapshotNode) -> str:
    parts = [node.role]
    if node.name:
        parts.append(json.dumps(node.name, ensure_ascii=False))
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
        if node.role == "text" and node.ref is None:
            out.append(f"{indent}- text: {node.name}")
            continue
        line = f"{indent}- {_head(node)}"
        children = node.children
        if node.value is not None:
            line += f": {_text(node.value)}"
        elif len(children) == 1 and children[0].role == "text" and children[0].ref is None:
            line += f": {children[0].name}"
            children = []
        elif children:
            line += ":"
        out.append(line)
        _lines(children, indent + "  ", out)


def render(nodes: list[SnapshotNode], *, max_chars: int | None = None) -> str:
    """Render *nodes* as ``- role "name" [state] [ref=eN]: value`` lines.

    With *max_chars*, whole lines are kept while they fit and a last line
    ``- [truncated: N more lines; ...]`` says what was cut.
    """
    if max_chars is not None and max_chars < 1:
        raise ValueError(f"max_chars must be >= 1, got {max_chars}")
    lines: list[str] = []
    _lines(nodes, "", lines)
    text = "\n".join(lines)
    if max_chars is None or len(text) <= max_chars:
        return text
    kept: list[str] = []
    size = 0
    for index, line in enumerate(lines):
        marker = (
            f"- [truncated: {len(lines) - index} more lines;"
            " narrow with selector=, depth= or interactive=True]"
        )
        if size + len(line) + 1 + len(marker) > max_chars:
            return "\n".join([*kept, marker])
        kept.append(line)
        size += len(line) + 1
    return text  # unreachable: the text did not fit

"""Text of a snapshot: the AX nodes pruned into :class:`SnapshotNode` trees, the
fusion of the page text pieces between them, and the
``- role "name" [state] [ref=eN]: "value"`` lines. Pure functions, no CDP.

Page text is quoted as JSON with control and bidi characters escaped and long
strings capped, so nothing a page writes can break a line or fake a ref.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tellurium.browser.snapshot import AXTree

_SPACES = re.compile(r"\s+")
# Page text longer than this is cut in the rendering, with a ``[+N chars]`` signal.
_MAX_TEXT = 300
# Left raw by json.dumps: C1 controls, bidi marks/overrides/isolates, separators.
_UNSAFE = re.compile("[\x7f-\x9f\u061c\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff]")

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


class Unread(str):
    """URL of a cross-site iframe left out of the snapshot; *state* says why."""

    def __new__(cls, url: str, state: str) -> Unread:
        unread = super().__new__(cls, url)
        unread.state = state
        return unread


@dataclass
class SnapshotNode:
    """One node of a snapshot. *ref* is ``None`` for text (``role == "text"``) and
    for an OOPIF placeholder (``states["oopif"]`` is ``True`` or why it was left out,
    URL in *name*); *states* may hold checked, pressed, expanded, disabled, selected, level."""

    ref: str | None
    role: str
    name: str
    value: str | None = None
    states: dict[str, bool | int | str] = field(default_factory=dict)
    children: list[SnapshotNode] = field(default_factory=list)


def squash(value: Any) -> str:
    """*value* as text with every run of white space turned into one space, trimmed."""
    return _SPACES.sub(" ", str(value)).strip()


def is_text(node: SnapshotNode) -> bool:
    """Whether *node* is page text rather than an element."""
    return node.role == "text" and node.ref is None


def fuse(children: list[SnapshotNode], name: str, value: str | None) -> list[SnapshotNode]:
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


def ax_role(node: dict[str, Any]) -> str:
    return (node.get("role") or {}).get("value") or ""


def ax_props(node: dict[str, Any]) -> dict[str, Any]:
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
        roots = (n.get("frameId") for n in tree.nodes if ax_role(n) == "RootWebArea")
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
        role = ax_role(node)
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
        props = ax_props(node)
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
            snap.children = fuse(self.children(node, level + 1, nesting), name, snap.value)
        return [snap]

    def iframe(
        self, node: dict[str, Any], name: str, level: int, nesting: int
    ) -> list[SnapshotNode]:
        # *nesting* carries on into the frame: the limit is for the whole walk
        frame = self.tree.frames.get(node.get("backendDOMNodeId") or 0)
        if isinstance(frame, str):
            state = frame.state if isinstance(frame, Unread) else True
            return [SnapshotNode(None, "iframe", frame, states={"oopif": state})]
        inner = _Pruner(frame, self.ref_for, self.interactive, self.depth) if frame else None
        if self.interactive:
            return inner.walk(None, level, nesting) if inner else []
        snap = SnapshotNode(
            self.ref_for(node["backendDOMNodeId"], self.frame, self.tree.owner), "iframe", name
        )
        snap.children = inner.walk(None, level + 1, nesting) if inner else []
        return [snap]


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
    return fuse(pruner.walk(root, 0, 0), "", None)


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
            parts.append("[oopif]" if state is True else f"[oopif: {state}]")
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
        if is_text(node):
            out.append(f"{indent}- text: {_quote(node.name)}")
            continue
        line, children = f"{indent}- {_head(node)}", node.children
        if node.value is not None:
            line += f": {_quote(squash(node.value))}"
        elif len(children) == 1 and is_text(children[0]):
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

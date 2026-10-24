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

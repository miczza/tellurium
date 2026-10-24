"""Element wrapper — interact with a single DOM node via CDP."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from tellurium.browser import geometry
from tellurium.browser.handles import elements_from_array, handles_of, resolve_node, send_on_handle

if TYPE_CHECKING:
    from tellurium.browser.tab import Tab
    from tellurium.cdp.transport._session import Session

# TreeWalker restricted to this element's subtree — the relative counterpart
# of Tab._TEXT_WALKER_JS.
_REL_TEXT_WALKER_JS = """
function(text, exact) {
    var results = [];
    var walker = document.createTreeWalker(this, NodeFilter.SHOW_TEXT, null, false);
    while (walker.nextNode()) {
        var node = walker.currentNode;
        var content = node.textContent.trim();
        if (!content) continue;
        var match = exact ? (content === text) : (content.indexOf(text) !== -1);
        if (match && node.parentElement) results.push(node.parentElement);
    }
    return [...new Set(results)];
}
"""

# XPath evaluated with this element as the context node.
_REL_XPATH_JS = """
function(expr) {
    var snap = document.evaluate(
        expr, this, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
    );
    var out = [];
    for (var i = 0; i < snap.snapshotLength; i++) out.push(snap.snapshotItem(i));
    return out;
}
"""


class Element:
    """Represents a DOM element backed by a CDP remote object.

    The element is addressed by its ``objectId``, which stays valid for the
    life of the document. A bare *nodeId* is not enough: every
    ``DOM.getDocument`` (issued by each Tab query) invalidates all nodeIds
    handed out before it, so producers resolve the objectId right away.

    All property accessors are async because they issue CDP calls.
    """

    _released, _finalizer = False, None  # also for Element.__new__ test doubles

    def __init__(
        self,
        session: Session,
        tab: Tab,
        node_id: int = 0,
        *,
        object_id: str | None = None,
    ):
        self._session = session
        self._tab = tab
        self._node_id = node_id
        self._object_id: str | None = None
        if object_id:
            self._bind(object_id)
        self._selector: str | None = (
            None  # CSS selector used to locate this element (for isolated-world queries)
        )
        self._frame_id: str | None = (
            None  # frame this element belongs to (None → use tab._frame_id)
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    async def _from_node_id(
        cls, session: Session, tab: Tab, node_id: int, selector: str | None = None
    ) -> Element:
        """Build an Element from a fresh *nodeId*, resolving it immediately."""
        element = cls(session, tab, node_id)
        element._selector = selector
        await element._resolve()
        return element

    def _bind(self, object_id: str) -> None:
        self._object_id = object_id
        handles = handles_of(self._tab)
        self._finalizer = handles.adopt(self, object_id) if handles else None

    async def _resolve(self) -> str:
        """Resolve *nodeId* to a remote *objectId* (cached) in the tab's group."""
        if self._object_id is None:
            self._bind(await resolve_node(self._session, self._tab, self._node_id, self._released))
        return self._object_id

    async def release(self) -> None:
        """Free this element's handle in the page; later calls raise ``StaleElementError``."""
        object_id, self._object_id, self._released = self._object_id, None, True
        if self._finalizer is not None:
            self._finalizer.detach()
        if object_id and (handles := handles_of(self._tab)):
            await handles.release(object_id)

    async def _call_raw(
        self, function_declaration: str, arguments: list | None = None, return_by_value: bool = True
    ) -> dict:
        """Run *Runtime.callFunctionOn* and return the raw remote object."""
        object_id = await self._resolve()
        params: dict[str, Any] = {
            "functionDeclaration": function_declaration,
            "objectId": object_id,
            "returnByValue": return_by_value,
            "awaitPromise": True,
        }
        if arguments:
            params["arguments"] = arguments
        result = await send_on_handle(self._session, "Runtime.callFunctionOn", params)
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise RuntimeError(remote.get("description", "callFunctionOn failed"))
        return remote

    async def _call(
        self, function_declaration: str, arguments: list | None = None, return_by_value: bool = True
    ) -> Any:
        """Run *Runtime.callFunctionOn* against this element's remote object."""
        remote = await self._call_raw(function_declaration, arguments, return_by_value)
        if remote.get("type") == "undefined":
            return None
        return remote.get("value")

    async def _call_elements(
        self, function_declaration: str, arguments: list | None = None
    ) -> list[Element]:
        """Call JS returning an array of nodes and map it to :class:`Element`s."""
        remote = await self._call_raw(function_declaration, arguments, return_by_value=False)
        array_id = remote.get("objectId")
        if not array_id or remote.get("subtype") != "array":
            return []
        return await elements_from_array(self._session, self._tab, array_id)

    async def _call_element(
        self, function_declaration: str, arguments: list | None = None
    ) -> Element | None:
        """Call JS returning a single node (or null) and map it to an Element."""
        remote = await self._call_raw(function_declaration, arguments, return_by_value=False)
        object_id = remote.get("objectId")
        if not object_id or remote.get("subtype") == "null":
            return None
        return Element(self._session, self._tab, object_id=object_id)

    async def _center(self) -> tuple[float, float]:
        """The (x, y) centre of the element's box, in page coordinates (Chrome's layout)."""
        return geometry.center(await geometry.content_box(self))

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    async def text(self) -> str:
        """Return the element's *own* visible text (design doc 03 §Element).

        Only direct child text nodes are concatenated — text inside nested
        elements is excluded — and the result is trimmed.  Use
        :meth:`text_all` for the full ``textContent`` of the subtree.

        For a leaf element (``<h1>Hi</h1>``) the two are identical; they
        differ for containers such as ``<li>Price <b>9.99</b></li>``, where
        ``text()`` is ``"Price"`` and ``text_all()`` is ``"Price 9.99"``.
        """
        val = await self._call(
            "function() {"
            "  var out = '';"
            "  for (var n = this.firstChild; n; n = n.nextSibling) {"
            "    if (n.nodeType === 3) out += n.nodeValue;"
            "  }"
            "  return out.trim();"
            "}"
        )
        return val or ""

    async def own_text(self) -> str:
        """Alias of :meth:`text` — direct child text nodes only."""
        return await self.text()

    async def text_all(self) -> str:
        """Return the element's full ``textContent`` (all descendants)."""
        val = await self._call("function() { return this.textContent; }")
        return val or ""

    async def tag(self) -> str:
        """Return the lower-cased tag name."""
        val = await self._call("function() { return this.tagName.toLowerCase(); }")
        return val or ""

    async def html(self) -> str:
        """Return the outer HTML of this element."""
        object_id = await self._resolve()
        result = await send_on_handle(self._session, "DOM.getOuterHTML", {"objectId": object_id})
        return result.get("outerHTML", "")

    async def attr(self, name: str) -> str | None:
        """Return a single attribute value, or *None* if missing."""
        return await self._call(
            "function(name) { return this.getAttribute(name); }",
            arguments=[{"value": name}],
        )

    async def attributes(self) -> dict[str, str]:
        """Return all attributes as a dict."""
        object_id = await self._resolve()
        result = await send_on_handle(self._session, "DOM.describeNode", {"objectId": object_id})
        flat = result.get("node", {}).get("attributes", [])
        return dict(zip(flat[::2], flat[1::2], strict=False))

    async def bounding_box(self) -> dict:
        """Return ``{x, y, width, height}`` from *getBoundingClientRect*."""
        return await self._call(
            "function() {"
            "  var r = this.getBoundingClientRect();"
            "  return {x: r.x, y: r.y, width: r.width, height: r.height};"
            "}"
        )

    async def bounding_box_isolated(self) -> dict:
        """Return {x, y, width, height} read in the human-sim isolated world.

        Safe against page-JS monkey-patches of Element.prototype.getBoundingClientRect.
        Falls back to main-world bounding_box() if the isolated world cannot be
        created (very old Chrome, renderer crash) or if no selector is cached
        on the element.

        Staleness note: the stashed ``_selector`` is re-resolved via
        ``document.querySelector`` in the isolated world at call time.  If the
        DOM has mutated between ``select()`` and the human action the rect may
        reflect a *different* element than this one.  The fallback path
        (``bounding_box()`` on this element's objectId) preserves identity.  Users who need stable identity should rely on the
        fallback (don't pass a selector, or use XPath-based selection).
        """
        import json

        from tellurium.stealth._isolated import get_hsim_world

        frame_id = getattr(self, "_frame_id", None) or self._tab._frame_id
        ctx = await get_hsim_world(self._tab, frame_id=frame_id)
        if ctx is None:
            return await self.bounding_box()

        selector = getattr(self, "_selector", None)
        if selector is None:
            return await self.bounding_box()

        expr = (
            f"(() => {{"
            f"  const el = document.querySelector({json.dumps(selector)});"
            f"  if (!el) return null;"
            f"  const r = el.getBoundingClientRect();"
            f"  return {{x: r.x, y: r.y, width: r.width, height: r.height}};"
            f"}})()"
        )
        resp = await self._session.send(
            "Runtime.evaluate",
            {
                "expression": expr,
                "contextId": ctx,
                "returnByValue": True,
            },
        )
        val = resp.get("result", {}).get("value")
        if val is None:
            return await self.bounding_box()
        return val

    async def children(self) -> list[Element]:
        """Return the direct element children (text nodes excluded)."""
        return await self._call_elements(
            "function() { return Array.prototype.slice.call(this.children); }"
        )

    async def parent(self) -> Element | None:
        """Return the parent element, or *None* for the document root."""
        return await self._call_element("function() { return this.parentElement; }")

    async def is_visible(self) -> bool:
        return (
            await self._call(
                "function() {"
                "  var s = window.getComputedStyle(this);"
                "  return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';"
                "}"
            )
            or False
        )

    async def is_enabled(self) -> bool:
        return not (await self._call("function() { return this.disabled; }") or False)

    async def is_checked(self) -> bool:
        return await self._call("function() { return this.checked; }") or False

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    async def click(self, human: bool = False) -> None:
        """Click the element.

        *human=False* — fast JS click.
        *human=True* — scroll into view, move cursor using Wind Mouse trajectory to a
        random point inside the bounding box, then dispatch real Input events.
        """
        if not human:
            await self._call("function() { this.click(); }")
        else:
            await geometry.human_click(self)  # Wind Mouse trajectory, box checked before press

    async def type(
        self,
        text: str,
        *,
        human: bool = False,
        clear: bool = False,
        wpm: float = 52,
        typos: bool = False,
    ) -> None:
        """Focus this element and type *text*.

        *clear=True* — clear the field value before typing.
        *human=True* — use HumanTyping with realistic inter-key intervals and dwell times.
        *wpm* — typing speed when *human=True* (default 52; higher = faster).
        *typos=True* — occasionally hit an adjacent QWERTY key, then correct it
        with Backspace (design doc 05 §"Typo Simulation", ~2%/char).  Requires
        *human=True*; opt-in because a stray keystroke can break a password or
        URL field.
        """
        await self.focus()
        if clear:
            await self._call(
                "function() { this.value = ''; this.dispatchEvent(new Event('input')); }"
            )
        # Delegates to Tab's human typing
        await self._tab.keyboard_type(text, human=human, wpm=wpm, typos=typos)

    async def upload(self, *files: str) -> None:
        """Set files on an ``<input type="file">`` element."""
        object_id = await self._resolve()
        await send_on_handle(
            self._session,
            "DOM.setFileInputFiles",
            {"objectId": object_id, "files": list(files)},
        )

    async def select_option(self, value: str) -> None:
        """Select an ``<option>`` by its *value* attribute inside a ``<select>``."""
        await self._call(
            "function(v) {"
            "  this.value = v;"
            "  this.dispatchEvent(new Event('change', {bubbles: true}));"
            "}",
            arguments=[{"value": value}],
        )

    async def hover(self) -> None:
        """Move the mouse to the centre of this element."""
        await self.scroll_into_view()
        x, y = await self._center()
        await self._tab.mouse_move(x, y)

    async def scroll_into_view(self, human: bool = False) -> None:
        if human:
            box = await geometry.content_box(self)  # top-level viewport coordinates
            viewport_height = await self._tab.eval("window.innerHeight")
            delta = box["y"] - (viewport_height or 800) / 3
            if abs(delta) > 50:
                await self._tab.scroll(delta_y=delta, human=True)
        else:
            await self._call(
                "function() { this.scrollIntoView({block: 'center', inline: 'center'}); }"
            )

    async def focus(self) -> None:
        object_id = await self._resolve()
        await send_on_handle(self._session, "DOM.focus", {"objectId": object_id})

    async def drag_to(self, target: Element, steps: int = 10) -> None:
        """Drag this element to *target* with intermediate mouse-move steps."""
        await self.scroll_into_view()
        sx, sy = await self._center()
        await target.scroll_into_view()
        tx, ty = await target._center()

        await self._tab.mouse_move(sx, sy)
        await self._tab._dispatch_mouse(
            {
                "type": "mousePressed",
                "x": sx,
                "y": sy,
                "button": "left",
                "clickCount": 1,
            }
        )
        for i in range(1, steps + 1):
            frac = i / steps
            mx = sx + (tx - sx) * frac
            my = sy + (ty - sy) * frac
            await self._tab.mouse_move(mx, my)
            await asyncio.sleep(0.01)
        await self._tab._dispatch_mouse(
            {
                "type": "mouseReleased",
                "x": tx,
                "y": ty,
                "button": "left",
                "clickCount": 1,
            }
        )

    # ------------------------------------------------------------------
    # Relative selection
    # ------------------------------------------------------------------

    async def select(self, selector: str) -> Element:
        """querySelector relative to this element."""
        element = await self._call_element(
            "function(s) { return this.querySelector(s); }", arguments=[{"value": selector}]
        )
        if element is None:
            raise LookupError(f"No element matching {selector!r} inside this element")
        return element

    async def select_all(self, selector: str) -> list[Element]:
        """querySelectorAll relative to this element."""
        return await self._call_elements(
            "function(s) { return Array.from(this.querySelectorAll(s)); }",
            arguments=[{"value": selector}],
        )

    async def find(self, text: str, *, exact: bool = False) -> Element:
        """Find a descendant by visible text.  Raises ``LookupError``."""
        matches = await self.find_all(text, exact=exact)
        if not matches:
            raise LookupError(f"No descendant containing text {text!r}")
        return matches[0]

    async def find_all(self, text: str, *, exact: bool = False) -> list[Element]:
        """Return every descendant whose own text matches *text*."""
        return await self._call_elements(
            _REL_TEXT_WALKER_JS,
            arguments=[{"value": text}, {"value": bool(exact)}],
        )

    async def xpath(self, expression: str) -> Element | None:
        """Evaluate an XPath *relative to this element*.  First match or None.

        Uses ``document.evaluate`` with this element as the context node, so
        ``"./div"`` and ``".//a"`` are resolved against it (unlike
        :meth:`Tab.xpath`, which searches the whole document).
        """
        matches = await self.xpath_all(expression)
        return matches[0] if matches else None

    async def xpath_all(self, expression: str) -> list[Element]:
        """Return every node matching an XPath relative to this element."""
        return await self._call_elements(_REL_XPATH_JS, arguments=[{"value": expression}])

    async def apply(self, js: str) -> Any:
        """Run arbitrary JS against this element.

        *js* should be a function body string, e.g. ``"function() { return this.id; }"``.
        Arrow functions like ``"el => el.id"`` are converted automatically.
        """
        if "=>" in js and not js.strip().startswith("function"):
            # Convert arrow: "el => el.id" -> "function(el) { return el.id; }"
            parts = js.split("=>", 1)
            params = parts[0].strip()
            body = parts[1].strip()
            if not params.startswith("("):
                params = f"({params})"
            if not body.startswith("{"):
                body = f"{{ return {body}; }}"
            js = f"function{params} {body}"
        return await self._call(js)

    async def screenshot(self, path: str | None = None) -> bytes:
        """Capture a screenshot of just this element."""
        await self.scroll_into_view()
        box = await self.bounding_box()
        clip = {
            "x": box["x"],
            "y": box["y"],
            "width": box["width"],
            "height": box["height"],
            "scale": 1,
        }
        result = await self._session.send(
            "Page.captureScreenshot",
            {"format": "png", "clip": clip},
        )
        import base64

        data = base64.b64decode(result["data"])
        if path:
            from pathlib import Path as P

            P(path).write_bytes(data)
        return data

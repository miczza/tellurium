"""Element wrapper — interact with a single DOM node via CDP."""
from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tellurium.cdp.transport._session import Session
    from tellurium.browser.tab import Tab


class Element:
    """Represents a DOM element backed by a CDP *nodeId*.

    All property accessors are async because they issue CDP calls.
    """

    def __init__(self, session: Session, tab: Tab, node_id: int):
        self._session = session
        self._tab = tab
        self._node_id = node_id
        self._object_id: str | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve(self) -> str:
        """Resolve *nodeId* to a remote *objectId* (cached)."""
        if self._object_id is None:
            result = await self._session.send(
                "DOM.resolveNode", {"nodeId": self._node_id}
            )
            self._object_id = result["object"]["objectId"]
        return self._object_id

    async def _call(self, function_declaration: str, arguments: list | None = None,
                    return_by_value: bool = True) -> Any:
        """Run *Runtime.callFunctionOn* against this element's remote object."""
        object_id = await self._resolve()
        params: dict[str, Any] = {
            "functionDeclaration": function_declaration,
            "objectId": object_id,
            "returnByValue": return_by_value,
            "awaitPromise": True,
        }
        if arguments:
            params["arguments"] = arguments
        result = await self._session.send("Runtime.callFunctionOn", params)
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise RuntimeError(remote.get("description", "callFunctionOn failed"))
        if remote.get("type") == "undefined":
            return None
        return remote.get("value")

    async def _center(self) -> tuple[float, float]:
        """Return the (x, y) centre of the element's bounding box."""
        box = await self.bounding_box()
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    async def text(self) -> str:
        """Return the element's ``textContent``."""
        val = await self._call("function() { return this.textContent; }")
        return val or ""

    async def tag(self) -> str:
        """Return the lower-cased tag name."""
        val = await self._call("function() { return this.tagName.toLowerCase(); }")
        return val or ""

    async def html(self) -> str:
        """Return the outer HTML of this element."""
        result = await self._session.send(
            "DOM.getOuterHTML", {"nodeId": self._node_id}
        )
        return result.get("outerHTML", "")

    async def attr(self, name: str) -> str | None:
        """Return a single attribute value, or *None* if missing."""
        return await self._call(
            "function(name) { return this.getAttribute(name); }",
            arguments=[{"value": name}],
        )

    async def attributes(self) -> dict[str, str]:
        """Return all attributes as a dict."""
        result = await self._session.send(
            "DOM.getAttributes", {"nodeId": self._node_id}
        )
        flat = result.get("attributes", [])
        return dict(zip(flat[::2], flat[1::2]))

    async def bounding_box(self) -> dict:
        """Return ``{x, y, width, height}`` from *getBoundingClientRect*."""
        return await self._call(
            "function() {"
            "  var r = this.getBoundingClientRect();"
            "  return {x: r.x, y: r.y, width: r.width, height: r.height};"
            "}"
        )

    async def is_visible(self) -> bool:
        return await self._call(
            "function() {"
            "  var s = window.getComputedStyle(this);"
            "  return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';"
            "}"
        ) or False

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
            await self.scroll_into_view()
            box = await self.bounding_box()
            x = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
            y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
            await self._tab.mouse_click(x, y, human=True)  # Uses Wind Mouse trajectory

    async def type(self, text: str, *, human: bool = False, clear: bool = False) -> None:
        """Focus this element and type *text*.

        *clear=True* — clear the field value before typing.
        *human=True* — use HumanTyping with realistic inter-key intervals and dwell times.
        """
        await self.focus()
        if clear:
            await self._call("function() { this.value = ''; this.dispatchEvent(new Event('input')); }")
        await self._tab.keyboard_type(text, human=human)  # Delegates to Tab's human typing

    async def upload(self, *files: str) -> None:
        """Set files on an ``<input type="file">`` element."""
        await self._session.send(
            "DOM.setFileInputFiles",
            {"nodeId": self._node_id, "files": list(files)},
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
            box = await self.bounding_box()
            viewport_height = await self._tab.eval("window.innerHeight")
            scroll_y = await self._tab.eval("window.scrollY")
            target_y = box["y"] - (viewport_height or 800) / 3
            delta = target_y - (scroll_y or 0)
            if abs(delta) > 50:
                await self._tab.scroll(delta_y=delta, human=True)
        else:
            await self._call(
                "function() { this.scrollIntoView({block: 'center', inline: 'center'}); }"
            )

    async def focus(self) -> None:
        await self._session.send("DOM.focus", {"nodeId": self._node_id})

    async def drag_to(self, target: Element, steps: int = 10) -> None:
        """Drag this element to *target* with intermediate mouse-move steps."""
        await self.scroll_into_view()
        sx, sy = await self._center()
        await target.scroll_into_view()
        tx, ty = await target._center()

        await self._tab.mouse_move(sx, sy)
        await self._session.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": sx, "y": sy, "button": "left", "clickCount": 1,
        })
        for i in range(1, steps + 1):
            frac = i / steps
            mx = sx + (tx - sx) * frac
            my = sy + (ty - sy) * frac
            await self._tab.mouse_move(mx, my)
            await asyncio.sleep(0.01)
        await self._session.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": tx, "y": ty, "button": "left", "clickCount": 1,
        })

    # ------------------------------------------------------------------
    # Relative selection
    # ------------------------------------------------------------------

    async def select(self, selector: str) -> Element:
        """querySelector relative to this element."""
        result = await self._session.send(
            "DOM.querySelector", {"nodeId": self._node_id, "selector": selector}
        )
        nid = result.get("nodeId", 0)
        if not nid:
            raise LookupError(f"No element matching {selector!r} inside this element")
        return Element(self._session, self._tab, nid)

    async def select_all(self, selector: str) -> list[Element]:
        """querySelectorAll relative to this element."""
        result = await self._session.send(
            "DOM.querySelectorAll", {"nodeId": self._node_id, "selector": selector}
        )
        return [
            Element(self._session, self._tab, nid)
            for nid in result.get("nodeIds", [])
        ]

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
            "x": box["x"], "y": box["y"],
            "width": box["width"], "height": box["height"],
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

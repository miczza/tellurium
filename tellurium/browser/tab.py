"""Tab wrapper — one browser tab backed by a CDP session."""
from __future__ import annotations

import asyncio
import base64
import random
import re
import time
from typing import TYPE_CHECKING, Any

from tellurium.browser.element import Element

if TYPE_CHECKING:
    from tellurium.cdp.transport._session import Session
    from tellurium.browser.browser import Browser

# JS snippet used by find() / find_all() to locate elements by visible text.
_TEXT_WALKER_JS = """
(function(text, exact) {
    var results = [];
    var walker = document.createTreeWalker(
        document.body, NodeFilter.SHOW_TEXT, null, false
    );
    while (walker.nextNode()) {
        var node = walker.currentNode;
        var content = node.textContent.trim();
        if (!content) continue;
        var match = exact ? (content === text) : (content.indexOf(text) !== -1);
        if (match && node.parentElement) {
            results.push(node.parentElement);
        }
    }
    // Deduplicate (same element may appear from adjacent text nodes)
    return [...new Set(results)];
})(%s, %s)
"""


class Tab:
    """High-level wrapper around a single browser tab (CDP target session)."""

    def __init__(self, session: Session, browser: Browser, target_id: str):
        self._session = session
        self._browser = browser
        self._target_id = target_id
        self._url: str = ""
        self._title: str = ""
        self._mouse_pos: tuple[float, float] = (0, 0)  # Track current mouse position
        self._action_timer = None  # Will be set when stealth is active
        self._capture_manager = None
        self._hsim_worlds: dict[str, int] = {}  # frame_id -> executionContextId, per-frame
        self._frame_id: str = ""  # main frame id, populated on first navigation

        def _on_frame_navigated(params: dict) -> None:
            frame = params.get("frame", {})
            fid = frame.get("id")
            if fid:
                self._hsim_worlds.pop(fid, None)
                # Track the main frame id (parentId absent means it's the main frame)
                if not frame.get("parentId"):
                    self._frame_id = fid

        self._session.on("Page.frameNavigated", _on_frame_navigated)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def get(self, url: str, *, wait_until: str = "load", timeout: float = 30) -> None:
        """Navigate to *url* and wait for the page to load."""
        await self._session.send("Page.enable", {})
        loaded = asyncio.get_running_loop().create_future()

        def _on_load(params: dict) -> None:
            if not loaded.done():
                loaded.set_result(True)

        self._session.on("Page.loadEventFired", _on_load)
        try:
            result = await self._session.send("Page.navigate", {"url": url})
            if "errorText" in result and result.get("errorText"):
                raise RuntimeError(f"Navigation failed: {result['errorText']}")
            await asyncio.wait_for(loaded, timeout=timeout)
        finally:
            self._session.off("Page.loadEventFired", _on_load)
        self._url = url

    async def back(self) -> None:
        """Go back in history."""
        history = await self._session.send("Page.getNavigationHistory", {})
        idx = history["currentIndex"]
        if idx > 0:
            entry = history["entries"][idx - 1]
            await self._session.send(
                "Page.navigateToHistoryEntry", {"entryId": entry["id"]}
            )

    async def forward(self) -> None:
        """Go forward in history."""
        history = await self._session.send("Page.getNavigationHistory", {})
        idx = history["currentIndex"]
        if idx < len(history["entries"]) - 1:
            entry = history["entries"][idx + 1]
            await self._session.send(
                "Page.navigateToHistoryEntry", {"entryId": entry["id"]}
            )

    async def reload(self) -> None:
        await self._session.send("Page.reload", {})

    @property
    def url(self) -> str:
        return self._url

    @property
    def title(self) -> str:
        return self._title

    async def wait_for_navigation(self, url: str | None = None, timeout: float = 30) -> None:
        """Wait for a navigation (frame-stopped-loading) event.

        If *url* is given, wait until the frame URL matches (substring match).
        """
        done = asyncio.get_running_loop().create_future()

        def _on_navigated(params: dict) -> None:
            if done.done():
                return
            new_url = params.get("url", params.get("frame", {}).get("url", ""))
            if url is None or url in new_url:
                done.set_result(new_url)

        await self._session.send("Page.enable", {})
        self._session.on("Page.frameNavigated", _on_navigated)
        try:
            result_url = await asyncio.wait_for(done, timeout=timeout)
            self._url = result_url
        finally:
            self._session.off("Page.frameNavigated", _on_navigated)

    # ------------------------------------------------------------------
    # JavaScript
    # ------------------------------------------------------------------

    async def eval(self, expression: str) -> Any:
        """Evaluate *expression* in the page and return the result.

        Uses ``Runtime.evaluate`` with ``returnByValue``/``awaitPromise``.
        Does **not** call ``Runtime.enable`` (anti-detection critical).
        """
        result = await self._session.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise RuntimeError(remote.get("description", "eval failed"))
        if remote.get("type") == "undefined":
            return None
        return remote.get("value")

    async def eval_on(self, selector: str, expression: str) -> Any:
        """Run JS on the first element matching *selector*.

        *expression* is a function body called with the element as ``this``.
        """
        doc = await self._session.send("DOM.getDocument", {"depth": 0})
        root_id = doc["root"]["nodeId"]
        query = await self._session.send(
            "DOM.querySelector", {"nodeId": root_id, "selector": selector}
        )
        node_id = query.get("nodeId", 0)
        if not node_id:
            raise LookupError(f"No element matching {selector!r}")
        resolve = await self._session.send("DOM.resolveNode", {"nodeId": node_id})
        object_id = resolve["object"]["objectId"]
        # Convert arrow functions
        fn = expression
        if "=>" in fn and not fn.strip().startswith("function"):
            parts = fn.split("=>", 1)
            params = parts[0].strip()
            body = parts[1].strip()
            if not params.startswith("("):
                params = f"({params})"
            if not body.startswith("{"):
                body = f"{{ return {body}; }}"
            fn = f"function{params} {body}"
        res = await self._session.send("Runtime.callFunctionOn", {
            "functionDeclaration": fn,
            "objectId": object_id,
            "returnByValue": True,
            "awaitPromise": True,
        })
        remote = res.get("result", {})
        if remote.get("type") == "undefined":
            return None
        return remote.get("value")

    async def add_script(self, source: str) -> str:
        """Add a script to evaluate on every new document.

        Returns the identifier that can be used to remove it later.
        """
        result = await self._session.send(
            "Page.addScriptToEvaluateOnNewDocument", {"source": source}
        )
        return result["identifier"]

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    async def _get_document_root(self) -> int:
        doc = await self._session.send("DOM.getDocument", {"depth": 0})
        return doc["root"]["nodeId"]

    async def select(self, selector: str, *, timeout: float = 10) -> Element:
        """Wait for a CSS-matching element and return it."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            root = await self._get_document_root()
            result = await self._session.send(
                "DOM.querySelector", {"nodeId": root, "selector": selector}
            )
            nid = result.get("nodeId", 0)
            if nid:
                el = Element(self._session, self, nid)
                el._selector = selector
                return el
            if asyncio.get_event_loop().time() >= deadline:
                raise TimeoutError(f"Timed out waiting for selector {selector!r}")
            await asyncio.sleep(0.2)

    async def select_all(self, selector: str) -> list[Element]:
        """Return all elements matching a CSS selector (no waiting)."""
        root = await self._get_document_root()
        result = await self._session.send(
            "DOM.querySelectorAll", {"nodeId": root, "selector": selector}
        )
        return [
            Element(self._session, self, nid)
            for nid in result.get("nodeIds", [])
        ]

    async def find(self, text: str, *, timeout: float = 10, exact: bool = False) -> Element:
        """Find an element by visible text content (polls until found or timeout)."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            elements = await self._find_text_elements(text, exact)
            if elements:
                return elements[0]
            if asyncio.get_event_loop().time() >= deadline:
                raise TimeoutError(f"Timed out waiting for text {text!r}")
            await asyncio.sleep(0.2)

    async def find_all(self, text: str, *, exact: bool = False) -> list[Element]:
        """Return all elements containing *text* (no waiting)."""
        return await self._find_text_elements(text, exact)

    async def _find_text_elements(self, text: str, exact: bool) -> list[Element]:
        """Use a TreeWalker JS snippet to locate elements by text."""
        js_text = _json_escape(text)
        js_exact = "true" if exact else "false"
        js = _TEXT_WALKER_JS % (js_text, js_exact)

        # Ensure the full DOM tree is populated in the CDP node map so that
        # DOM.requestNode can map remote object IDs to nodeIds.
        await self._session.send("DOM.getDocument", {"depth": -1})

        result = await self._session.send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": False,
            "awaitPromise": False,
        })
        remote = result.get("result", {})
        if remote.get("type") != "object" or remote.get("subtype") != "array":
            return []

        # Get the array's length
        arr_id = remote["objectId"]
        props = await self._session.send("Runtime.getProperties", {
            "objectId": arr_id,
            "ownProperties": True,
        })
        elements: list[Element] = []
        for prop in props.get("result", []):
            if not prop["name"].isdigit():
                continue
            obj = prop.get("value", {})
            obj_id = obj.get("objectId")
            if not obj_id:
                continue
            # Request the node for this object
            node_result = await self._session.send(
                "DOM.requestNode", {"objectId": obj_id}
            )
            nid = node_result.get("nodeId", 0)
            if nid:
                elements.append(Element(self._session, self, nid))
        return elements

    async def xpath(self, expression: str, *, timeout: float = 10) -> Element | None:
        """Evaluate an XPath expression. Returns first match or *None*."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            doc = await self._session.send("DOM.getDocument", {"depth": 0})
            root_id = doc["root"]["nodeId"]
            result = await self._session.send(
                "DOM.performSearch", {"query": expression}
            )
            search_id = result.get("searchId", "")
            count = result.get("resultCount", 0)
            if count:
                nodes = await self._session.send(
                    "DOM.getSearchResults",
                    {"searchId": search_id, "fromIndex": 0, "toIndex": 1},
                )
                nids = nodes.get("nodeIds", [])
                if nids and nids[0]:
                    return Element(self._session, self, nids[0])
            if asyncio.get_event_loop().time() >= deadline:
                return None
            await asyncio.sleep(0.2)

    async def wait_for(self, selector: str, *, timeout: float = 30) -> Element:
        """Wait for a CSS selector to appear (longer default timeout)."""
        return await self.select(selector, timeout=timeout)

    # ------------------------------------------------------------------
    # Screenshots / content
    # ------------------------------------------------------------------

    async def screenshot(self, path: str | None = None, *, full_page: bool = False,
                         format: str = "png") -> bytes:
        """Capture a screenshot of the visible viewport or full page."""
        params: dict[str, Any] = {"format": format}
        if full_page:
            metrics = await self._session.send("Page.getLayoutMetrics", {})
            content_size = metrics.get("contentSize", metrics.get("cssContentSize", {}))
            params["clip"] = {
                "x": 0, "y": 0,
                "width": content_size.get("width", 1920),
                "height": content_size.get("height", 1080),
                "scale": 1,
            }
        result = await self._session.send("Page.captureScreenshot", params)
        data = base64.b64decode(result["data"])
        if path:
            from pathlib import Path as P
            P(path).write_bytes(data)
        return data

    async def content(self) -> str:
        """Return the full page HTML."""
        doc = await self._session.send("DOM.getDocument", {"depth": 0})
        root_id = doc["root"]["nodeId"]
        result = await self._session.send(
            "DOM.getOuterHTML", {"nodeId": root_id}
        )
        return result.get("outerHTML", "")

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    async def mouse_move(self, x: float, y: float, human: bool = False) -> None:
        if human:
            from tellurium.stealth.human import wind_mouse, apply_lognormal_velocity, MOUSE_PROFILES
            params = MOUSE_PROFILES["normal"]
            path = wind_mouse(*self._mouse_pos, x, y, **params["wind"])
            timed_path = apply_lognormal_velocity(path, mu=params["mu"], sigma=params["sigma"])
            t_start = time.monotonic()
            for px, py, t_ms in timed_path:
                target_time = t_start + t_ms / 1000
                now = time.monotonic()
                if target_time > now:
                    await asyncio.sleep(target_time - now)
                await self._session.send("Input.dispatchMouseEvent", {
                    "type": "mouseMoved", "x": px, "y": py,
                })
            self._mouse_pos = (x, y)
        else:
            await self._session.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": x, "y": y,
            })
            self._mouse_pos = (x, y)

    async def mouse_click(self, x: float, y: float, button: str = "left", human: bool = False) -> None:
        if human:
            await self.mouse_move(x, y, human=True)
            await asyncio.sleep(random.uniform(0.1, 0.3))  # reaction time
        await self._session.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": button, "clickCount": 1,
        })
        await asyncio.sleep(random.uniform(0.08, 0.15) if human else 0.05)
        await self._session.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": button, "clickCount": 1,
        })

    async def click_in_iframe(
        self, iframe_selector: str, x: float, y: float,
        *, button: str = "left", human: bool = False,
    ) -> None:
        """Click at (x, y) inside an iframe, translating to viewport coords.

        CDP Input.dispatchMouseEvent uses viewport coordinates. Passing
        iframe-local coords directly produces "click too small" detection
        on Cloudflare Turnstile and similar widgets. This helper resolves
        the iframe's getBoundingClientRect in the parent-frame isolated
        world (safe against page-JS monkey-patches of
        getBoundingClientRect), adds the rect origin to the iframe-local
        coords, and dispatches via mouse_click(human=human).

        Raises ValueError if iframe_selector matches no element.
        """
        from tellurium.stealth._isolated import get_hsim_world
        import json

        ctx = await get_hsim_world(self, frame_id=self._frame_id)
        expr = (
            f"(() => {{"
            f"  const f = document.querySelector({json.dumps(iframe_selector)});"
            f"  if (!f) return null;"
            f"  const r = f.getBoundingClientRect();"
            f"  return {{x: r.x, y: r.y}};"
            f"}})()"
        )
        params: dict = {"expression": expr, "returnByValue": True}
        if ctx is not None:
            params["contextId"] = ctx
        resp = await self._session.send("Runtime.evaluate", params)
        rect = resp.get("result", {}).get("value")
        if rect is None:
            raise ValueError(
                f"click_in_iframe: no iframe matched selector {iframe_selector!r}"
            )

        abs_x = rect["x"] + x
        abs_y = rect["y"] + y
        await self.mouse_click(abs_x, abs_y, button=button, human=human)

    async def keyboard_press(self, key: str) -> None:
        """Press a single key or key combo (e.g. ``"Enter"``, ``"Control+a"``)."""
        modifiers = 0
        parts = key.split("+")
        actual_key = parts[-1]
        for mod in parts[:-1]:
            mod_lower = mod.lower()
            if mod_lower in ("ctrl", "control"):
                modifiers |= 2
            elif mod_lower in ("alt",):
                modifiers |= 1
            elif mod_lower in ("shift",):
                modifiers |= 8
            elif mod_lower in ("meta", "cmd", "command"):
                modifiers |= 4

        await self._session.send("Input.dispatchKeyEvent", {
            "type": "keyDown", "key": actual_key, "modifiers": modifiers,
        })
        await self._session.send("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": actual_key, "modifiers": modifiers,
        })

    async def keyboard_type(
        self, text: str, human: bool = False, wpm: float = 52
    ) -> None:
        """Type a string character-by-character via ``Input.dispatchKeyEvent``.

        When ``human=True``, ``wpm`` tunes the typing speed (words per minute,
        5 chars/word). Default 52 ≈ average human. Higher = faster.
        """
        if human:
            from tellurium.stealth.human import HumanTyping, apply_key_rollover
            typer = HumanTyping(wpm=wpm)
            events = apply_key_rollover(typer.get_events(text))
            for event in events:
                if event["delay_ms"] > 0:
                    await asyncio.sleep(event["delay_ms"] / 1000)
                char = event["key"]
                key_code = ord(char.upper()) if len(char) == 1 and char.isascii() else 0
                code = f"Key{char.upper()}" if char.isalpha() else ""
                if event["type"] == "rawKeyDown":
                    await self._session.send("Input.dispatchKeyEvent", {
                        "type": "rawKeyDown", "key": char, "code": code,
                        "windowsVirtualKeyCode": key_code,
                    })
                elif event["type"] == "char":
                    await self._session.send("Input.dispatchKeyEvent", {
                        "type": "char", "text": char, "key": char,
                    })
                elif event["type"] == "keyUp":
                    await self._session.send("Input.dispatchKeyEvent", {
                        "type": "keyUp", "key": char, "code": code,
                        "windowsVirtualKeyCode": key_code,
                    })
        else:
            for char in text:
                await self._session.send("Input.dispatchKeyEvent", {
                    "type": "keyDown", "key": char, "text": char,
                })
                await self._session.send("Input.dispatchKeyEvent", {
                    "type": "keyUp", "key": char,
                })

    async def scroll(self, delta_y: float = 0, delta_x: float = 0,
                     x: float | None = None, y: float | None = None,
                     human: bool = False) -> None:
        """Dispatch a mouse wheel event."""
        if human and delta_y != 0:
            from tellurium.stealth.human import HumanScroll
            scroller = HumanScroll()
            await scroller.scroll_by(self._session, delta_y, x or 400, y or 300)
        else:
            await self._session.send("Input.dispatchMouseEvent", {
                "type": "mouseWheel", "x": x or 0, "y": y or 0,
                "deltaX": delta_x, "deltaY": delta_y,
            })

    # ------------------------------------------------------------------
    # Wait helpers
    # ------------------------------------------------------------------

    async def wait(self, seconds: float) -> None:
        """Sleep for *seconds* (convenience wrapper)."""
        await asyncio.sleep(seconds)

    async def wait_for_url(self, url: str, *, timeout: float = 30) -> None:
        """Poll until the page URL contains *url*."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            current = await self.eval("window.location.href")
            if current and url in current:
                self._url = current
                return
            if asyncio.get_event_loop().time() >= deadline:
                raise TimeoutError(f"Timed out waiting for URL containing {url!r}")
            await asyncio.sleep(0.25)

    # ------------------------------------------------------------------
    # Network capture
    # ------------------------------------------------------------------

    async def capture(self, log: bool = False, log_filter: str | None = None) -> None:
        """Start capturing network requests."""
        if self._capture_manager is None:
            from tellurium.capture.manager import CaptureManager
            self._capture_manager = CaptureManager(self._session)
        await self._capture_manager.start(log=log, log_filter=log_filter)

    async def capture_stop(self) -> None:
        """Stop capturing network requests."""
        if self._capture_manager:
            await self._capture_manager.stop()

    async def requests(self, **filters) -> list:
        """Search captured requests."""
        if self._capture_manager is None:
            return []
        if "body_contains" in filters:
            body_contains = filters.pop("body_contains")
            return await self._capture_manager.search_body(body_contains, **filters)
        return self._capture_manager.search(**filters)

    async def wait_for_request(self, url_pattern: str, timeout: float = 30):
        """Wait for a request matching the pattern."""
        if self._capture_manager is None:
            from tellurium.capture.manager import CaptureManager
            self._capture_manager = CaptureManager(self._session)
            await self._capture_manager.start()
        return await self._capture_manager.wait_for(url_pattern, timeout)

    async def record(self, url_pattern: str = "*"):
        """Start recording network requests for export."""
        from tellurium.capture.recorder import Recorder
        if self._capture_manager is None:
            from tellurium.capture.manager import CaptureManager
            self._capture_manager = CaptureManager(self._session)
            await self._capture_manager.start()
        return Recorder(self._capture_manager, url_pattern)

    # ------------------------------------------------------------------
    # Raw CDP
    # ------------------------------------------------------------------

    async def send_cdp(self, method: str, params: dict | None = None) -> dict:
        """Send a raw CDP command on this tab's session."""
        return await self._session.send(method, params)


def _json_escape(s: str) -> str:
    """Return a JS string literal for *s*, properly escaped."""
    import json
    return json.dumps(s)

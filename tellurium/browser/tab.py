"""Tab wrapper — one browser tab backed by a CDP session."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tellurium.browser.dialog import DialogGuard, DialogHandler
from tellurium.browser.download import DownloadWaiter, TabFrames, expect_tab_download
from tellurium.browser.element import Element
from tellurium.browser.handles import (
    HandleGroup,
    StaleElementError,
    as_stale,
    elements_from_array,
)
from tellurium.browser.navigation import (
    check_wait_until,
    navigate,
    poll_url,
    step_history,
    url_matches,
    wait_for_main_frame,
)
from tellurium.browser.refs import RefMap, resolve_ref
from tellurium.browser.snapshot import FETCH_TIMEOUT, MAX_DOM_NODES, SnapshotNode, render
from tellurium.browser.snapshot import take_snapshot_nodes as _snapshot_nodes
from tellurium.cdp.types import CDPError

logger = logging.getLogger("tellurium")

if TYPE_CHECKING:
    from tellurium.browser.browser import Browser
    from tellurium.cdp.transport._session import Session

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


# eval_on: called on the element. A compile error never runs it, so the
# caller may retry *expression* as a body; anything thrown is returned.
_EVAL_ON_JS = (
    "async function() { try { const __f = %s;\n"
    "return {ok: true, value: await (typeof __f === 'function' ? __f.call(this, this) : __f)}; "
    "} catch (e) { return {ok: false, error: String((e && e.stack) || e)}; } }"
)

__all__ = ["Tab", "url_matches"]


class Tab:
    """High-level wrapper around a single browser tab (CDP target session)."""

    # Class-level defaults so a Tab built with ``Tab.__new__`` (test doubles)
    # still behaves; ``__init__`` shadows each of them per instance.
    _action_timer = None
    _idle_simulator = None
    _screen_offset: tuple[float, float] | None = None
    _screen_parity_done: bool = False
    _window_id: int | None = None
    _mouse_profile: str = "normal"
    _typo_rng = None

    def __init__(
        self,
        session: Session,
        browser: Browser,
        target_id: str,
        *,
        stealth_idle: bool = False,
        mouse_profile: str = "normal",
        dialogs: str = "dismiss",
    ):
        from tellurium.stealth.human import MOUSE_PROFILES

        if mouse_profile not in MOUSE_PROFILES:
            raise ValueError(
                f"Unknown mouse_profile {mouse_profile!r}; expected one of {sorted(MOUSE_PROFILES)}"
            )
        self._mouse_profile = mouse_profile
        self._typo_rng = None  # lazily seeded from the stealth profile
        self._session = session
        self._dialogs = DialogGuard(session, dialogs)
        self._handles = HandleGroup(session)
        self._refs = RefMap()  # snapshot refs, a generation per main-frame document
        self._frames = TabFrames(session, target_id)  # routes iframe downloads here
        self._browser = browser
        self._target_id = target_id
        self._url: str = ""
        self._title: str = ""
        self._lifecycle_enabled = False
        self._closed = False
        self._mouse_pos: tuple[float, float] = (0, 0)  # Track current mouse position
        self._action_timer = None  # ActionTimer, created on first human action
        # Design doc 05 "Idle Simulation" — Browser.launch(stealth_idle=True)
        self._idle_simulator = None
        if stealth_idle:
            from tellurium.stealth.idle import IdleSimulator

            self._idle_simulator = IdleSimulator()
        self._capture_manager = None
        self._hsim_worlds: dict[str, int] = {}  # frame_id -> executionContextId, per-frame
        self._frame_id: str = ""  # main frame id, populated on first navigation
        # P0.4 screenX/screenY parity — resolved lazily on first mouse input
        self._screen_offset: tuple[float, float] | None = None
        self._screen_parity_done: bool = False
        self._window_id: int | None = None

        def _on_frame_navigated(params: dict) -> None:
            frame = params.get("frame", {})
            fid = frame.get("id")
            if fid:
                self._hsim_worlds.pop(fid, None)
                # Track the main frame id (parentId absent means it's the main frame)
                if not frame.get("parentId"):
                    self._frame_id = fid
                    self._handles.rotate()  # the old document's handles are gone
                    self._refs.reset()

        self._session.on("Page.frameNavigated", _on_frame_navigated)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def get(self, url: str, *, wait_until: str = "load", timeout: float = 30) -> None:
        """Navigate to *url* and wait for the page to reach *wait_until*.

        ``wait_until``:

        * ``"commit"`` — return once the navigation is committed
        * ``"domcontentloaded"`` — the ``DOMContentLoaded`` event fired
        * ``"load"`` — the ``load`` event fired (all subresources done)
        * ``"networkidle"`` — no network activity for 500 ms after load

        A same-document navigation (``#fragment``) returns right away: there
        is no new document to wait for. *timeout* covers the whole navigation;
        on expiry :class:`NavigationTimeoutError` (a ``TimeoutError``) names
        the URL and the phase. A refused navigation raises ``NavigationError``.
        """
        check_wait_until(wait_until)
        info = await navigate(
            self._session,
            url,
            wait_until=wait_until,
            timeout=timeout,
            dialogs=self._dialogs,
            prepare=self._enable_lifecycle_events,
        )
        self._url = url
        if info is not None:
            self._title, self._url = info[0], info[1] or url
        if self._action_timer is not None:
            # Design doc 05: navigate -> click / navigate -> type carry their
            # own (longer) transition delays.
            self._action_timer.mark("navigate")

    async def _enable_lifecycle_events(self) -> None:
        if self._lifecycle_enabled:
            return
        await self._session.send("Page.enable", {}, timeout=10)
        await self._session.send("Page.setLifecycleEventsEnabled", {"enabled": True}, timeout=10)
        self._lifecycle_enabled = True

    async def close(self) -> None:
        """Close this tab. Further commands on it raise ``ConnectionError``."""
        if not self._closed:
            self._dialogs.close()
            try:
                await self._handles.close()
            finally:
                await self._browser._close_tab(self)

    @property
    def closed(self) -> bool:
        return self._closed

    def on_dialog(self, handler: DialogHandler | None) -> None:
        """Call *handler* (sync or async) with each :class:`Dialog` the page opens.

        The handler decides with ``dialog.accept(text)`` / ``dialog.dismiss()``;
        an undecided dialog gets the tab policy (``Browser.launch(dialogs=...)``,
        default ``"dismiss"``). ``None`` removes the handler.
        """
        self._dialogs.set_handler(handler)

    async def back(self) -> None:
        """Go back in history."""
        await step_history(self._session, -1)

    async def forward(self) -> None:
        """Go forward in history."""
        await step_history(self._session, 1)

    async def reload(self) -> None:
        await self._session.send("Page.reload", {})

    @property
    def url(self) -> str:
        return self._url

    @property
    def title(self) -> str:
        """Document title as of the last :meth:`get` (see :meth:`eval` for live)."""
        return self._title

    async def wait_for_navigation(self, url: str | None = None, timeout: float = 30) -> None:
        """Wait for the main frame to navigate and fire ``load``.

        If *url* is given, wait until the new URL matches it — glob pattern
        when it contains ``*`` or ``?``, substring match otherwise. Iframe
        navigations are ignored. Raises :class:`NavigationTimeoutError`.
        """
        await self._enable_lifecycle_events()
        self._url = await wait_for_main_frame(self._session, url, timeout=timeout)

    # ------------------------------------------------------------------
    # JavaScript
    # ------------------------------------------------------------------

    async def eval(self, expression: str, timeout: float | None = None) -> Any:
        """Evaluate *expression* in the page and return the result.

        Uses ``Runtime.evaluate`` with ``returnByValue``/``awaitPromise``; *timeout*
        defaults to the session's (30 s). Never calls ``Runtime.enable``.
        """
        result = await self._session.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise RuntimeError(remote.get("description", "eval failed"))
        if remote.get("type") == "undefined":
            return None
        return remote.get("value")

    async def eval_on(self, selector: str, expression: str, timeout: float | None = None) -> Any:
        """Run JS on the first element matching *selector* and return the result.

        *expression* is a function (``"el => el.id"``, ``"() => this.id"``,
        ``"function() { return this.id; }"``), called with the element as ``this``
        and as its argument; an expression (``"this.id"``); or a function body
        (``"return this.id"``). A JavaScript exception raises ``RuntimeError``.
        *timeout* bounds each CDP command (default: the session's, 30 s).
        """
        send = self._session.send
        doc = await send("DOM.getDocument", {"depth": 0}, timeout=timeout)
        query = await send(
            "DOM.querySelector",
            {"nodeId": doc["root"]["nodeId"], "selector": selector},
            timeout=timeout,
        )
        node_id = query.get("nodeId", 0)
        if not node_id:
            raise LookupError(f"No element matching {selector!r}")
        node = {"nodeId": node_id, "objectGroup": self._handles.name}
        object_id = (await send("DOM.resolveNode", node, timeout=timeout))["object"]["objectId"]
        call = {"objectId": object_id, "returnByValue": True, "awaitPromise": True}
        try:  # as a function or an expression; else, if it does not compile, as a body
            for source in (f"(\n{expression}\n)", f"function() {{\n{expression}\n}}"):
                call["functionDeclaration"] = _EVAL_ON_JS % source
                res = await send("Runtime.callFunctionOn", call, timeout=timeout)
                if "exceptionDetails" not in res:  # it ran: the wrapper caught any throw
                    break
        finally:
            self._handles.discard(object_id)
        out = res.get("result", {}).get("value") or {}
        if not out.get("ok"):
            error = out.get("error") or res.get("result", {}).get("description")
            raise RuntimeError(f"eval_on({selector!r}) failed: {error}")
        return out.get("value")

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

    async def _element_or_none(self, node_id: int, selector: str | None = None) -> Element | None:
        """Resolve a just-queried node; ``None`` if a navigation removed it meanwhile."""
        try:
            return await Element._from_node_id(self._session, self, node_id, selector)
        except CDPError:
            return None

    async def _query_selector(self, selector: str) -> Element | None:
        """First match of *selector*; ``None`` also when the document was swapped mid-query."""
        try:
            root = await self._get_document_root()
            result = await self._session.send(
                "DOM.querySelector", {"nodeId": root, "selector": selector}
            )
        except CDPError as exc:  # a navigation replaced the root between the two calls
            if not isinstance(as_stale(exc), StaleElementError):
                raise  # e.g. an invalid selector
            return None
        nid = result.get("nodeId", 0)
        return await self._element_or_none(nid, selector) if nid else None

    async def select(self, selector: str, *, timeout: float = 10) -> Element:
        """Wait for a CSS-matching element and return it; ``"@e3"`` is :meth:`ref`."""
        if selector.startswith("@"):  # never CSS: a ref, or a LookupError naming the form
            return await self.ref(selector)
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            element = await self._query_selector(selector)
            if element is not None:
                return element
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Timed out waiting for selector {selector!r}")
            await asyncio.sleep(0.2)

    async def snapshot(
        self,
        *,
        interactive: bool = False,
        selector: str | None = None,
        depth: int | None = None,
        max_chars: int | None = None,
        **limits: Any,
    ) -> str:
        """The page as text for an LLM, ``- button "Sign in" [ref=e3]`` per line, cut past
        *max_chars* with a signal. Options and *limits* as in :meth:`snapshot_nodes`."""
        opts = {"interactive": interactive, "selector": selector, "depth": depth}
        return render(await self.snapshot_nodes(**opts, **limits), max_chars=max_chars)

    async def snapshot_nodes(
        self,
        *,
        interactive: bool = False,
        selector: str | None = None,
        depth: int | None = None,
        max_nodes: int | None = MAX_DOM_NODES,
        snapshot_timeout: float = FETCH_TIMEOUT,
    ) -> list[SnapshotNode]:
        """The page's accessibility tree as :class:`SnapshotNode` trees: only usable
        nodes (*interactive*), the first *selector* match's subtree, *depth* levels.
        Over *max_nodes* DOM nodes or *snapshot_timeout* s: ``SnapshotTooLargeError``.
        A node keeps its ref until the main frame navigates; act on it with :meth:`ref`."""
        opts = {"interactive": interactive, "selector": selector, "depth": depth}
        limits = {"max_nodes": max_nodes, "snapshot_timeout": snapshot_timeout}
        return await _snapshot_nodes(self._session, self._refs, **opts, **limits)

    async def ref(self, ref: str) -> Element:
        """The element of a snapshot ref (``"e3"`` or ``"@e3"``). ``StaleElementError``
        if it is from an earlier document or the node left the page, ``LookupError``
        if no snapshot gave it out."""
        return await resolve_ref(self._session, self, self._refs, ref)

    def expect_download(self, timeout: float = 30) -> DownloadWaiter:
        """``async with tab.expect_download() as info: <start it>``, then
        ``download = await info.value``: the next download of this tab (iframes too)."""
        return expect_tab_download(self, timeout)

    async def select_all(self, selector: str, *, timeout: float = 0) -> list[Element]:
        """Return all elements matching a CSS selector, polling up to *timeout* s for one.

        The default ``0`` returns at once, possibly an empty list (counting matches,
        maybe zero, must not block); an expired timeout gives ``[]``, not an error.
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            root = await self._get_document_root()
            result = await self._session.send(
                "DOM.querySelectorAll", {"nodeId": root, "selector": selector}
            )
            found = [await self._element_or_none(nid) for nid in result.get("nodeIds", [])]
            elements = [element for element in found if element is not None]
            if elements or asyncio.get_running_loop().time() >= deadline:
                return elements
            await asyncio.sleep(0.2)

    async def find(self, text: str, *, timeout: float = 10, exact: bool = False) -> Element:
        """Find an element by visible text content (polls until found or timeout)."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            elements = await self._find_text_elements(text, exact)
            if elements:
                return elements[0]
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Timed out waiting for text {text!r}")
            await asyncio.sleep(0.2)

    async def find_all(
        self, text: str, *, timeout: float = 0, exact: bool = False
    ) -> list[Element]:
        """Return all elements containing *text*.

        *timeout* — seconds to keep polling until at least one match appears
        (default ``0``: return immediately, possibly empty).  Returns an empty
        list on expiry rather than raising, unlike :meth:`find`.
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            elements = await self._find_text_elements(text, exact)
            if elements or asyncio.get_running_loop().time() >= deadline:
                return elements
            await asyncio.sleep(0.2)

    async def _find_text_elements(self, text: str, exact: bool) -> list[Element]:
        """Use a TreeWalker JS snippet to locate elements by text."""
        js_text = _json_escape(text)
        js_exact = "true" if exact else "false"
        js = _TEXT_WALKER_JS % (js_text, js_exact)

        result = await self._session.send(
            "Runtime.evaluate",
            {
                "expression": js,
                "returnByValue": False,
                "awaitPromise": False,
                "objectGroup": self._handles.name,
            },
        )
        remote = result.get("result", {})
        if remote.get("type") != "object" or remote.get("subtype") != "array":
            return []

        return await elements_from_array(self._session, self, remote["objectId"])

    async def _xpath_once(self, expression: str, limit: int | None) -> list[Element]:
        """One ``DOM.performSearch``, at most *limit* nodes. ``DOM.getDocument`` primes the
        DOM agent; the result set is always released with ``DOM.discardSearchResults``
        (without it each poll leaked one set in the DOM agent for the tab's lifetime)."""
        await self._session.send("DOM.getDocument", {"depth": 0})
        result = await self._session.send("DOM.performSearch", {"query": expression})
        search_id, count = result.get("searchId", ""), result.get("resultCount", 0)
        try:
            if not count:
                return []
            window = {"searchId": search_id, "fromIndex": 0, "toIndex": min(count, limit or count)}
            nodes = await self._session.send("DOM.getSearchResults", window)
            found = [await self._element_or_none(n) for n in nodes.get("nodeIds", []) if n]
            return [element for element in found if element is not None]
        finally:
            if search_id:
                try:
                    await self._session.send("DOM.discardSearchResults", {"searchId": search_id})
                except Exception:  # noqa: BLE001 — best effort, must never break input
                    pass

    async def _poll_xpath(self, expression: str, timeout: float, limit: int | None = None):
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            elements = await self._xpath_once(expression, limit)
            if elements or asyncio.get_running_loop().time() >= deadline:
                return elements
            await asyncio.sleep(0.2)

    async def xpath(self, expression: str, *, timeout: float = 10) -> Element | None:
        """First node matching an XPath expression, polled for up to *timeout* s; or *None*."""
        found = await self._poll_xpath(expression, timeout, limit=1)
        return found[0] if found else None

    async def xpath_all(self, expression: str, *, timeout: float = 0) -> list[Element]:
        """Every node matching an XPath expression, polling up to *timeout* s for one
        (default ``0``: return immediately, possibly empty)."""
        return await self._poll_xpath(expression, timeout)

    async def wait_for(
        self, selector: str, *, state: str = "visible", timeout: float = 30
    ) -> Element | None:
        """Wait until *selector* reaches *state* (design doc 03 §Attesa).

        ``state``:

        * ``"attached"`` — present in the DOM (returns the :class:`Element`)
        * ``"visible"`` — attached *and* rendered (non-zero box, not
          ``display:none`` / ``visibility:hidden`` / ``opacity:0``); returns
          the :class:`Element`
        * ``"hidden"`` — either detached or attached but not rendered
        * ``"detached"`` — no longer present in the DOM

        The two negative states return ``None``.  A timeout raises
        :class:`TimeoutError`.
        """
        if state not in ("visible", "hidden", "attached", "detached"):
            raise ValueError(
                f"Unknown state {state!r}; expected one of "
                "'visible', 'hidden', 'attached', 'detached'"
            )
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            element = await self._query_selector(selector)

            if state == "attached" and element is not None:
                return element
            if state == "detached" and element is None:
                return None
            if state in ("visible", "hidden"):
                visible = bool(element is not None and await element.is_visible())
                if state == "visible" and visible:
                    return element
                if state == "hidden" and not visible:
                    return None

            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Timed out waiting for selector {selector!r} to be {state}")
            await asyncio.sleep(0.2)

    # ------------------------------------------------------------------
    # Screenshots / content
    # ------------------------------------------------------------------

    async def screenshot(
        self,
        path: str | None = None,
        *,
        full_page: bool = False,
        quality: int | None = None,
        format: str = "png",
        timeout: float | None = None,
    ) -> bytes:
        """Capture a screenshot of the visible viewport or full page.

        *quality* (0-100) only applies to lossy formats (``"jpeg"``,
        ``"webp"``); Chrome rejects it for PNG, so it is dropped with a
        warning instead of failing the call. *timeout* bounds each CDP
        command (default: the session's, 30 s; a tall full page may need more).
        """
        params: dict[str, Any] = {"format": format}
        if quality is not None:
            if format == "png":
                logger.warning(
                    "screenshot(quality=%s) ignored: quality only applies to "
                    "lossy formats (jpeg, webp), not png.",
                    quality,
                )
            else:
                params["quality"] = int(quality)
        if full_page:
            metrics = await self._session.send("Page.getLayoutMetrics", {}, timeout=timeout)
            content_size = metrics.get("contentSize", metrics.get("cssContentSize", {}))
            params["clip"] = {
                "x": 0,
                "y": 0,
                "width": content_size.get("width", 1920),
                "height": content_size.get("height", 1080),
                "scale": 1,
            }
        result = await self._session.send("Page.captureScreenshot", params, timeout=timeout)
        data = base64.b64decode(result["data"])
        if path:
            await asyncio.to_thread(Path(path).write_bytes, data)
        return data

    async def content(self) -> str:
        """Return the full page HTML."""
        root_id = await self._get_document_root()
        result = await self._session.send("DOM.getOuterHTML", {"nodeId": root_id})
        return result.get("outerHTML", "")

    async def pdf(
        self, path: str | None = None, *, timeout: float | None = None, **opts: Any
    ) -> bytes:
        """Render the page to PDF via ``Page.printToPDF`` and return the bytes.

        *path* — when given, the bytes are also written there.
        *opts* — forwarded verbatim as ``Page.printToPDF`` parameters
        (``landscape``, ``printBackground``, ``scale``, ``paperWidth``,
        ``paperHeight``, ``marginTop``, ``pageRanges``, ``preferCSSPageSize``…).
        ``printBackground=True`` is the default here because a PDF without
        backgrounds rarely matches what the page looks like. *timeout* bounds
        the command (default: the session's, 30 s).

        Chrome only implements ``Page.printToPDF`` in headless mode; a headed
        browser answers with a CDP error ("PrintToPDF is not implemented").
        """
        params: dict[str, Any] = {"printBackground": True, "transferMode": "ReturnAsBase64"}
        params.update(opts)
        result = await self._session.send("Page.printToPDF", params, timeout=timeout)
        data = base64.b64decode(result.get("data", ""))
        if path:
            await asyncio.to_thread(Path(path).write_bytes, data)
        return data

    # ------------------------------------------------------------------
    # Window
    # ------------------------------------------------------------------

    async def _get_window_id(self) -> int | None:
        """Resolve (and cache) this tab's browser window id, or *None*."""
        if self._window_id is not None:
            return self._window_id
        try:
            resp = await self._browser._router.root.send(
                "Browser.getWindowForTarget",
                {"targetId": self._target_id},
                timeout=5.0,
            )
        except Exception:  # noqa: BLE001 — not implemented on every target type
            return None
        self._window_id = resp.get("windowId")
        return self._window_id

    async def _set_window_bounds(self, bounds: dict) -> bool:
        """Send ``Browser.setWindowBounds``; return False when unavailable."""
        window_id = await self._get_window_id()
        if window_id is None:
            return False
        try:
            await self._browser._router.root.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": bounds,
                },
                timeout=5.0,
            )
        except Exception:  # noqa: BLE001 — degrade, never break the caller
            return False
        # Window geometry changed → the cached screenX/screenY offset is stale.
        self._screen_offset = None
        return True

    async def set_viewport(self, width: int, height: int) -> None:
        """Resize the browser window to *width* x *height*.

        Resizing is done with ``Browser.setWindowBounds``, which moves the real
        window — every JS-visible metric (``innerWidth``, ``outerWidth``,
        ``screenX``…) stays self-consistent.  ``--window-size`` cannot be
        changed after launch, so it is not an option here.

        Fallback: if ``Browser.setWindowBounds`` is unavailable (older
        headless shells, non-top-level targets) the call degrades to
        ``Emulation.setDeviceMetricsOverride`` and logs a warning — that
        command is itself a detection signal (it desynchronises
        ``window.outerWidth``/``screen`` from the emulated viewport), so
        prefer ``Browser.launch(viewport=(w, h))`` when stealth matters.
        """
        if await self._set_window_bounds(
            {
                "width": int(width),
                "height": int(height),
                "windowState": "normal",
            }
        ):
            return
        logger.warning(
            "Browser.setWindowBounds unavailable; falling back to "
            "Emulation.setDeviceMetricsOverride, which is a detectable "
            "fingerprint signal. Prefer Browser.launch(viewport=(%d, %d)).",
            int(width),
            int(height),
        )
        await self._session.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": int(width),
                "height": int(height),
                "deviceScaleFactor": 0,
                "mobile": False,
            },
        )

    async def maximize(self) -> None:
        """Maximize the browser window (no-op when unavailable)."""
        await self._set_window_bounds({"windowState": "maximized"})

    async def minimize(self) -> None:
        """Minimize the browser window (no-op when unavailable)."""
        await self._set_window_bounds({"windowState": "minimized"})

    async def bring_to_front(self) -> None:
        """Focus this tab / bring its window to the foreground."""
        await self._session.send("Page.bringToFront", {})

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    # -- Inter-action timing (design doc 05) ---------------------------

    def _get_action_timer(self):
        """Lazily create this tab's :class:`ActionTimer`."""
        if self._action_timer is None:
            from tellurium.stealth.human import ActionTimer

            self._action_timer = ActionTimer()
        return self._action_timer

    async def _human_action(self, action: str) -> None:
        """Apply the inter-action delay before a ``human=True`` action."""
        await self._get_action_timer().delay_between(action)

    # -- P0.4: screenX/screenY parity ---------------------------------

    async def _eval_isolated(self, expression: str) -> Any:
        """Evaluate *expression* in the human-sim isolated world (best effort).

        Falls back to the main world when the isolated world is unavailable
        (e.g. before the first navigation). Never calls ``Runtime.enable``.
        """
        from tellurium.stealth._isolated import get_hsim_world

        params: dict = {"expression": expression, "returnByValue": True}
        ctx = await get_hsim_world(self, frame_id=self._frame_id)
        if ctx is not None:
            params["contextId"] = ctx
        resp = await self._session.send("Runtime.evaluate", params)
        return resp.get("result", {}).get("value")

    async def window_offset(self) -> tuple[float, float]:
        """Offset (dx, dy) between viewport coords and screen coords.

        ``dx`` is the window origin on screen, ``dy`` the window origin plus
        the height of the browser chrome UI (tab strip + omnibox), estimated
        as ``window.outerHeight - window.innerHeight`` per design doc 04
        §P0.4. Cached per tab; the cache is only invalidated by a new Tab.

        Primary source is ``Browser.getWindowForTarget`` (its reply already
        embeds ``bounds``; ``Browser.getWindowBounds`` is used as a second
        hop when it does not). Both are browser-level commands and *are*
        available on the stock backend over ``--remote-debugging-pipe``
        (verified on Chrome 153). Should they ever be unavailable — they are
        not implemented on Android/WebView targets — the fallback is
        ``window.screenX`` / ``window.screenY`` read from the page itself.
        """
        if self._screen_offset is not None:
            return self._screen_offset

        left: float | None = None
        top: float | None = None
        outer_height: float = 0.0
        try:
            root = self._browser._router.root
            resp = await root.send(
                "Browser.getWindowForTarget",
                {"targetId": self._target_id},
                timeout=5.0,
            )
            self._window_id = resp.get("windowId")
            bounds = resp.get("bounds") or {}
            if not bounds and self._window_id is not None:
                bounds = (
                    await root.send(
                        "Browser.getWindowBounds",
                        {"windowId": self._window_id},
                        timeout=5.0,
                    )
                ).get("bounds", {})
            if bounds:
                left = float(bounds.get("left") or 0)
                top = float(bounds.get("top") or 0)
                outer_height = float(bounds.get("height") or 0)
        except Exception:  # noqa: BLE001 — best effort, must never break input
            left = top = None  # fall through to the JS fallback

        chrome_ui = 0.0
        try:
            values = await self._eval_isolated(
                "[window.screenX, window.screenY, window.outerHeight, window.innerHeight]"
            )
            if isinstance(values, list) and len(values) == 4:
                if left is None or top is None:
                    left = float(values[0] or 0)
                    top = float(values[1] or 0)
                inner_height = float(values[3] or 0)
                # window.outerHeight reads 0 on a freshly created headed
                # window until the WM has mapped it; the CDP window bounds
                # height is the robust second source.
                outer = float(values[2] or 0) or outer_height
                chrome_ui = max(0.0, outer - inner_height)
        except Exception:  # noqa: BLE001 — best effort, must never break input
            pass

        offset = (float(left or 0), float(top or 0) + chrome_ui)
        self._screen_offset = offset
        return offset

    async def _ensure_screen_parity(self) -> None:
        """Make CDP-dispatched mouse events carry realistic screenX/screenY.

        Design doc 04 §P0.4 assumed Chrome sets ``screenX = clientX`` for
        ``Input.dispatchMouseEvent``. That is **no longer true**: measured on
        Chrome 153 stock (both headed and headless), the browser already adds
        the window origin and the chrome-UI height itself —
        ``screenX - clientX == window.screenX`` and
        ``screenY - clientY == window.screenY + (outerHeight - innerHeight)``,
        and both follow the window as it is moved. ``Input.dispatchMouseEvent``
        has no ``screenX``/``screenY`` parameters either, so adding an offset
        to ``x``/``y`` would move the *click itself* and produce a screen
        coordinate that is wrong twice over.

        What is left to fix is the degenerate window placement where the
        offset really is zero (window pinned at screen origin with no frame,
        which happens in headless): there ``screenX === clientX`` exactly,
        which is the signal Turnstile keys on. We then move the window to a
        plausible origin — no JS override, no invented per-event maths, the
        coordinates stay the browser's own.

        No-op when the backend advertises ``native_cdp_fix`` (patched engine
        fixes this in ``input_handler.cc``) or when stealth is off.
        """
        if self._screen_parity_done:
            return
        self._screen_parity_done = True

        browser = getattr(self, "_browser", None)
        if getattr(browser, "_stealth_engine", None) is None:
            return
        try:
            engine = getattr(browser, "_engine", None)
            if engine is not None and "native_cdp_fix" in engine.capabilities():
                return
        except Exception:  # noqa: BLE001 — best effort, must never break input
            pass

        try:
            dx, dy = await self.window_offset()
            if dx > 0 and dy > 0:
                return
            if self._window_id is None:
                return
            left = random.randint(22, 140)
            top = random.randint(18, 96)
            await self._browser._router.root.send(
                "Browser.setWindowBounds",
                {
                    "windowId": self._window_id,
                    "bounds": {"left": left, "top": top},
                },
                timeout=5.0,
            )
            self._screen_offset = None  # recompute against the new origin
            await self.window_offset()
        except Exception:  # noqa: BLE001 — best effort, must never break input
            pass  # best effort: never break input on a parity tweak

    async def _dispatch_mouse(self, params: dict) -> None:
        """Send ``Input.dispatchMouseEvent`` after the P0.4 parity check."""
        await self._ensure_screen_parity()
        await self._session.send("Input.dispatchMouseEvent", params)

    async def mouse_move(self, x: float, y: float, human: bool = False) -> None:
        if human:
            from tellurium.stealth.human import MOUSE_PROFILES, apply_lognormal_velocity, wind_mouse

            params = MOUSE_PROFILES[self._mouse_profile]
            path = wind_mouse(*self._mouse_pos, x, y, **params["wind"])
            timed_path = apply_lognormal_velocity(path, mu=params["mu"], sigma=params["sigma"])
            t_start = time.monotonic()
            for px, py, t_ms in timed_path:
                target_time = t_start + t_ms / 1000
                now = time.monotonic()
                if target_time > now:
                    await asyncio.sleep(target_time - now)
                await self._dispatch_mouse(
                    {
                        "type": "mouseMoved",
                        "x": px,
                        "y": py,
                    }
                )
            self._mouse_pos = (x, y)
        else:
            await self._dispatch_mouse(
                {
                    "type": "mouseMoved",
                    "x": x,
                    "y": y,
                }
            )
            self._mouse_pos = (x, y)

    async def mouse_click(
        self, x: float, y: float, button: str = "left", human: bool = False
    ) -> None:
        if human:
            await self._human_action("click")
            await self.mouse_move(x, y, human=True)
            await asyncio.sleep(random.uniform(0.1, 0.3))  # reaction time
        await self._dispatch_mouse(
            {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": button,
                "clickCount": 1,
            }
        )
        await asyncio.sleep(random.uniform(0.08, 0.15) if human else 0.05)
        await self._dispatch_mouse(
            {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": button,
                "clickCount": 1,
            }
        )

    async def click_in_iframe(
        self,
        iframe_selector: str,
        x: float,
        y: float,
        *,
        button: str = "left",
        human: bool = False,
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
            raise ValueError(f"click_in_iframe: no iframe matched selector {iframe_selector!r}")

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

        await self._session.send(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown",
                "key": actual_key,
                "modifiers": modifiers,
            },
        )
        await self._session.send(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": actual_key,
                "modifiers": modifiers,
            },
        )

    #: Named keys that the human-typing path may emit, with their Windows
    #: virtual key codes (Chrome needs the code to act on the key).
    _NAMED_KEYS = {"Backspace": 8, "Enter": 13, "Tab": 9, "Delete": 46, "Escape": 27}

    async def _dispatch_named_key(self, key: str, event_type: str) -> None:
        """Dispatch one half of a named-key press (no ``text`` payload)."""
        if event_type == "char":
            return  # named keys produce no character
        await self._session.send(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown" if event_type == "rawKeyDown" else "keyUp",
                "key": key,
                "code": key,
                "windowsVirtualKeyCode": self._NAMED_KEYS.get(key, 0),
                "nativeVirtualKeyCode": self._NAMED_KEYS.get(key, 0),
            },
        )

    def _get_typo_rng(self):
        """Random source for typo decisions, seeded from the stealth profile.

        One generator per tab, so repeated ``typos=True`` calls differ from
        each other yet the whole session replays identically for a given
        ``Browser.launch(seed=...)``.  Without a stealth profile the global
        :mod:`random` module is used.
        """
        if self._typo_rng is None:
            seed = getattr(getattr(self._browser, "_stealth_profile", None), "seed", None)
            self._typo_rng = random.Random(seed) if seed is not None else random
        return self._typo_rng

    async def keyboard_type(
        self,
        text: str,
        human: bool = False,
        wpm: float = 52,
        typos: bool = False,
    ) -> None:
        """Type a string character-by-character via ``Input.dispatchKeyEvent``.

        When ``human=True``, ``wpm`` tunes the typing speed (words per minute,
        5 chars/word). Default 52 ≈ average human. Higher = faster.

        ``typos=True`` (requires ``human=True``) occasionally hits an adjacent
        QWERTY key and corrects it with a real ``Backspace`` keystroke —
        design doc 05 §"Typo Simulation", ~2% per character.
        """
        if typos and not human:
            raise ValueError("keyboard_type(typos=True) requires human=True")
        if human:
            from tellurium.stealth.human import HumanTyping, apply_key_rollover

            await self._human_action("type")
            typer = HumanTyping(
                wpm=wpm,
                typos=typos,
                rng=self._get_typo_rng() if typos else None,
            )
            events = apply_key_rollover(typer.get_events(text))
            for event in events:
                if event["delay_ms"] > 0:
                    await asyncio.sleep(event["delay_ms"] / 1000)
                char = event["key"]
                if len(char) > 1:
                    # Named key (Backspace from the typo simulation): no text
                    # payload, otherwise Chrome inserts the literal word.
                    await self._dispatch_named_key(char, event["type"])
                    continue
                key_code = ord(char.upper()) if len(char) == 1 and char.isascii() else 0
                code = f"Key{char.upper()}" if char.isalpha() else ""
                if event["type"] == "rawKeyDown":
                    if char.isalpha():
                        # Letters: rawKeyDown + char event sequence
                        await self._session.send(
                            "Input.dispatchKeyEvent",
                            {
                                "type": "rawKeyDown",
                                "key": char,
                                "code": code,
                                "windowsVirtualKeyCode": key_code,
                            },
                        )
                    else:
                        # Special chars: keyDown with text (like non-human path)
                        await self._session.send(
                            "Input.dispatchKeyEvent",
                            {
                                "type": "keyDown",
                                "key": char,
                                "text": char,
                            },
                        )
                elif event["type"] == "char":
                    # Skip char event for non-alpha chars (keyDown already has text)
                    if char.isalpha():
                        await self._session.send(
                            "Input.dispatchKeyEvent",
                            {
                                "type": "char",
                                "text": char,
                                "key": char,
                            },
                        )
                elif event["type"] == "keyUp":
                    if char.isalpha():
                        await self._session.send(
                            "Input.dispatchKeyEvent",
                            {
                                "type": "keyUp",
                                "key": char,
                                "code": code,
                                "windowsVirtualKeyCode": key_code,
                            },
                        )
                    else:
                        await self._session.send(
                            "Input.dispatchKeyEvent",
                            {
                                "type": "keyUp",
                                "key": char,
                            },
                        )
        else:
            for char in text:
                await self._session.send(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyDown",
                        "key": char,
                        "text": char,
                    },
                )
                await self._session.send(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyUp",
                        "key": char,
                    },
                )

    async def scroll(
        self,
        delta_y: float = 0,
        delta_x: float = 0,
        x: float | None = None,
        y: float | None = None,
        human: bool = False,
    ) -> None:
        """Dispatch a mouse wheel event."""
        if human and delta_y != 0:
            from tellurium.stealth.human import HumanScroll

            await self._human_action("scroll")
            scroller = HumanScroll()
            await self._ensure_screen_parity()
            await scroller.scroll_by(self._session, delta_y, x or 400, y or 300)
        else:
            await self._dispatch_mouse(
                {
                    "type": "mouseWheel",
                    "x": x or 0,
                    "y": y or 0,
                    "deltaX": delta_x,
                    "deltaY": delta_y,
                }
            )

    # ------------------------------------------------------------------
    # Wait helpers
    # ------------------------------------------------------------------

    async def wait(self, seconds: float) -> None:
        """Sleep for *seconds*.

        With ``Browser.launch(stealth_idle=True)`` the wait is filled with
        low-amplitude background mouse activity instead of a perfectly still
        cursor (design doc 05 "Idle Simulation"). The idle loop never
        overshoots *seconds*.
        """
        if self._idle_simulator is not None:
            self._idle_simulator.update_pos(*self._mouse_pos)
            await self._idle_simulator.idle(self, seconds)
            return
        await asyncio.sleep(seconds)

    async def wait_for_url(self, url: str, *, timeout: float = 30) -> None:
        """Poll until the page URL matches *url*.

        *url* is a glob pattern (``"*/dashboard*"``) when it contains ``*`` or
        ``?``; otherwise it is matched as a substring, as before.
        """
        self._url = await poll_url(lambda: self.eval("window.location.href"), url, timeout)

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

    def intercept(self, url_pattern: str = "*"):
        """Return an InterceptStream for request interception.

        Usage:
            async with tab.intercept("*/api/*") as stream:
                async for request in stream:
                    if "blocked" in request.url:
                        await request.abort()
                    else:
                        await request.continue_()

        Note: More invasive than capture() — use only when you need to
        modify, block, or respond to requests. Every paused request MUST
        receive continue_(), abort(), or respond() or the page hangs.
        """
        from tellurium.capture.intercept import InterceptStream

        return InterceptStream(self._session, url_pattern)

    # ------------------------------------------------------------------
    # Raw CDP
    # ------------------------------------------------------------------

    async def send_cdp(self, method: str, params: dict | None = None) -> dict:
        """Send a raw CDP command on this tab's session."""
        return await self._session.send(method, params)


def _json_escape(s: str) -> str:
    """Return a JS string literal for *s*, properly escaped."""
    return json.dumps(s)

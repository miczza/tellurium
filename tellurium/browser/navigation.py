"""Navigation of a tab's main frame: one deadline, errors that name the cause.

``Page.navigate`` only answers once the response headers arrive, so the
deadline covers the command *and* the lifecycle wait: a server that holds the
response can no longer stall :meth:`Tab.get` past its timeout.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import math
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tellurium.browser.dialog import DialogGuard
    from tellurium.cdp.transport._session import Session

logger = logging.getLogger("tellurium")

# Tab.get(wait_until=...) -> Page.lifecycleEvent name (None: return on commit).
WAIT_UNTIL_EVENTS: dict[str, str | None] = {
    "commit": None,
    "domcontentloaded": "DOMContentLoaded",
    "load": "load",
    "networkidle": "networkIdle",
}

#: The deadline of a :meth:`Tab.get` given no ``timeout``, read at each call: a
#: machine whose disk freezes for seconds (a CI runner taking a shadow copy) may
#: raise it for a run.
NAVIGATION_TIMEOUT = 30.0
#: Bounds ``Page.enable`` and ``Page.setLifecycleEventsEnabled`` before a navigation.
LIFECYCLE_TIMEOUT = 10.0

# Bounds the cleanup and bookkeeping calls around a navigation.
_SHORT_TIMEOUT = 5.0
# Share of the deadline kept for Page.stopLoading once a navigation gives up.
_STOP_RESERVE = 0.5


class NavigationTimeoutError(TimeoutError):
    """A navigation did not reach *phase* within *timeout* seconds.

    ``phase`` is ``"commit"`` (no response from the server yet), the
    ``wait_until`` state that was awaited (``"load"``…), or ``"navigation"``
    for :meth:`Tab.wait_for_navigation`.
    """

    def __init__(self, url: str, phase: str, timeout: float, hint: str = ""):
        self.url = url
        self.phase = phase
        self.timeout = timeout
        super().__init__(f"Navigation to {url} did not reach {phase!r} within {timeout}s{hint}")


class NavigationError(RuntimeError):
    """Chrome refused or aborted a navigation (``errorText`` of ``Page.navigate``)."""

    def __init__(self, url: str, error_text: str):
        self.url = url
        self.error_text = error_text
        message = f"Navigation to {url} failed: {error_text}"
        if error_text == "net::ERR_ABORTED":
            message += (
                " (no document was committed: an HTTP 204/205 response, a download,"
                " or a navigation cancelled by the page; use Tab.expect_download()"
                " to capture a download)"
            )
        super().__init__(message)


def check_wait_until(wait_until: str) -> str | None:
    """Return the lifecycle event for *wait_until*, or raise ``ValueError``."""
    if wait_until not in WAIT_UNTIL_EVENTS:
        raise ValueError(
            f"Unknown wait_until {wait_until!r}; expected one of {sorted(WAIT_UNTIL_EVENTS)}"
        )
    return WAIT_UNTIL_EVENTS[wait_until]


def navigation_timeout(timeout: float | None) -> float:
    """*timeout*, else :data:`NAVIGATION_TIMEOUT` as it is now."""
    return NAVIGATION_TIMEOUT if timeout is None else timeout


class LifecycleEvents:
    """The ``Page`` domain and its lifecycle events of a session, which a
    navigation waits on: enabled once, by the first :meth:`enable` that succeeds."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._enabled = False

    async def enable(self) -> None:
        if self._enabled:
            return
        await self._session.send("Page.enable", {}, timeout=LIFECYCLE_TIMEOUT)
        params = {"enabled": True}
        await self._session.send(
            "Page.setLifecycleEventsEnabled", params, timeout=LIFECYCLE_TIMEOUT
        )
        self._enabled = True


def url_matches(pattern: str, url: str) -> bool:
    """Match *url* against *pattern*.

    A pattern containing ``*`` or ``?`` is matched with
    :func:`fnmatch.fnmatchcase`; anything else is a substring match, so
    ``wait_for_url("/dashboard")`` keeps working.
    """
    if not url:
        return False
    if "*" in pattern or "?" in pattern:
        return fnmatch.fnmatchcase(url, pattern)
    return pattern in url


async def step_history(session: Session, step: int, timeout: float = _SHORT_TIMEOUT) -> None:
    """Go *step* entries back (``-1``) or forward (``1``) in history; a no-op at either end."""
    history = await session.send("Page.getNavigationHistory", {}, timeout=timeout)
    index = history["currentIndex"] + step
    if 0 <= index < len(history["entries"]):
        entry = {"entryId": history["entries"][index]["id"]}
        await session.send("Page.navigateToHistoryEntry", entry, timeout=timeout)


async def poll_url(read_url: Callable[[], Awaitable[str | None]], url: str, timeout: float) -> str:
    """Poll *read_url* until it matches *url* (see :func:`url_matches`); return it."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        current = await read_url()
        if url_matches(url, current or ""):
            return current or ""
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"Timed out waiting for URL containing {url!r}")
        await asyncio.sleep(0.25)


def _dialog_hint(dialogs: DialogGuard | None) -> str:
    last = dialogs.last if dialogs is not None else None
    if last is None or last.handled:
        return ""
    return f"; a {last.type} dialog is still open: {last.message!r}"


async def navigate(
    session: Session,
    url: str,
    *,
    wait_until: str,
    timeout: float,
    dialogs: DialogGuard | None = None,
    prepare: Callable[[], Awaitable[None]] | None = None,
) -> tuple[str, str] | None:
    """Navigate the main frame to *url* and wait for *wait_until*, all within *timeout*.

    *prepare* (enabling lifecycle events) runs first, inside the deadline. On
    expiry the load is stopped, still within *timeout*, and
    :class:`NavigationTimeoutError` is raised. Returns ``(title, href)`` of the
    new document, or ``None`` when no time is left to read them.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    reserve = min(_STOP_RESERVE, timeout / 10)
    event_name = check_wait_until(wait_until)
    events: list[dict] = []
    arrived = asyncio.Event()
    phase = "commit"

    def _on_lifecycle(params: dict) -> None:
        events.append(params)
        arrived.set()

    async def _run() -> None:
        nonlocal phase
        if prepare is not None:
            await prepare()
        # Bounded by the outer deadline, not by the session default (30 s).
        result = await session.send("Page.navigate", {"url": url}, timeout=math.inf)
        if result.get("errorText"):
            raise NavigationError(url, result["errorText"])
        loader_id = result.get("loaderId")
        if event_name is not None and loader_id:
            phase = wait_until
            await wait_lifecycle(events, arrived, result.get("frameId"), loader_id, event_name)

    session.on("Page.lifecycleEvent", _on_lifecycle)
    try:
        await asyncio.wait_for(_run(), timeout=timeout - reserve)
    except TimeoutError:
        await stop_loading(session, max(deadline - loop.time(), 0.01))
        raise NavigationTimeoutError(url, phase, timeout, _dialog_hint(dialogs)) from None
    finally:
        session.off("Page.lifecycleEvent", _on_lifecycle)
    remaining = deadline - loop.time()
    return await document_info(session, remaining) if remaining > 0 else None


async def wait_for_main_frame(session: Session, pattern: str | None, *, timeout: float) -> str:
    """Wait for the main frame to commit a document (matching *pattern*) and load it.

    Iframe navigations are ignored. The wait is bound to the ``loaderId`` of
    the latest matching commit, so the ``load`` of an earlier document in a
    redirect chain does not end it. A back/forward-cache restore fires no
    ``load`` (the page was never unloaded): its commit ends the wait. Returns
    the new URL. Lifecycle events must already be enabled on *session*.
    """
    loads: set[str] = set()
    arrived = asyncio.Event()
    committed: dict = {}
    phase = "navigation"

    def _on_navigated(params: dict) -> None:
        frame = params.get("frame", {})
        if frame.get("parentId"):
            return
        if pattern is None or url_matches(pattern, frame.get("url", "")):
            committed.clear()
            committed.update(frame, restored=params.get("type") == "BackForwardCacheRestore")
            arrived.set()

    def _on_lifecycle(params: dict) -> None:
        if params.get("name") == "load" and params.get("loaderId"):
            loads.add(params["loaderId"])
            arrived.set()

    async def _run() -> None:
        nonlocal phase
        while not committed or not (committed["restored"] or committed.get("loaderId") in loads):
            if committed:
                phase = "load"
            arrived.clear()
            await arrived.wait()

    session.on("Page.frameNavigated", _on_navigated)
    session.on("Page.lifecycleEvent", _on_lifecycle)
    try:
        await asyncio.wait_for(_run(), timeout=timeout)
    except TimeoutError:
        raise NavigationTimeoutError(pattern or "any URL", phase, timeout) from None
    finally:
        session.off("Page.frameNavigated", _on_navigated)
        session.off("Page.lifecycleEvent", _on_lifecycle)
    return committed.get("url", "")


async def stop_loading(session: Session, timeout: float = _SHORT_TIMEOUT) -> None:
    """Best-effort ``Page.stopLoading`` after a navigation gave up."""
    try:
        await session.send("Page.stopLoading", {}, timeout=timeout)
    except Exception:  # noqa: BLE001 — the timeout error matters, not this
        logger.debug("Page.stopLoading failed", exc_info=True)


async def document_info(
    session: Session, timeout: float = _SHORT_TIMEOUT
) -> tuple[str, str] | None:
    """Return ``(title, href)`` of the current document, or ``None`` if unreadable.

    Bounded: a page that stopped answering must not stall the navigation that
    just succeeded.
    """
    try:
        result = await session.send(
            "Runtime.evaluate",
            {"expression": "[document.title, location.href]", "returnByValue": True},
            timeout=min(timeout, _SHORT_TIMEOUT),
        )
    except Exception:  # noqa: BLE001 — never worth failing a navigation
        logger.debug("Could not read document title/url", exc_info=True)
        return None
    value = result.get("result", {}).get("value")
    if not isinstance(value, list) or len(value) != 2:
        return None
    return value[0] or "", value[1] or ""


async def wait_lifecycle(
    events: list[dict], arrived: asyncio.Event, frame_id: str | None, loader_id: str, name: str
) -> None:
    """Wait for lifecycle event *name* of the document loaded by *loader_id*.

    A client-side redirect commits a new document in the same frame: its
    ``init`` event hands over the loader we wait on.
    """
    seen = 0
    while True:
        while seen < len(events):
            event = events[seen]
            seen += 1
            if frame_id and event.get("frameId") != frame_id:
                continue
            if event.get("name") == "init" and event.get("loaderId") != loader_id:
                loader_id = event.get("loaderId")
            elif event.get("loaderId") == loader_id and event.get("name") == name:
                return
        arrived.clear()
        await arrived.wait()

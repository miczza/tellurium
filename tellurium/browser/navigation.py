"""Navigation of a tab's main frame: one deadline, errors that name the cause.

``Page.navigate`` only answers once the response headers arrive, so the
deadline covers the command *and* the lifecycle wait: a server that holds the
response can no longer stall :meth:`Tab.get` past its timeout.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
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

# Bounds the cleanup and bookkeeping calls around a navigation.
_SHORT_TIMEOUT = 5.0

# On Python 3.10 asyncio.TimeoutError is not the builtin TimeoutError: keep
# both catchable there; on 3.11+ they are the same class.
_TIMEOUT_BASES: tuple[type, ...] = (
    (TimeoutError,)
    if asyncio.TimeoutError is TimeoutError
    else (TimeoutError, asyncio.TimeoutError)
)


class NavigationTimeoutError(*_TIMEOUT_BASES):  # type: ignore[misc]
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
                " or a navigation cancelled by the page)"
            )
        super().__init__(message)


def check_wait_until(wait_until: str) -> str | None:
    """Return the lifecycle event for *wait_until*, or raise ``ValueError``."""
    if wait_until not in WAIT_UNTIL_EVENTS:
        raise ValueError(
            f"Unknown wait_until {wait_until!r}; expected one of {sorted(WAIT_UNTIL_EVENTS)}"
        )
    return WAIT_UNTIL_EVENTS[wait_until]


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
) -> None:
    """Navigate the main frame to *url* and wait for *wait_until*, all within *timeout*.

    Lifecycle events must already be enabled on *session*. On expiry the
    load is stopped and :class:`NavigationTimeoutError` is raised.
    """
    event_name = check_wait_until(wait_until)
    events: list[dict] = []
    arrived = asyncio.Event()
    phase = "commit"

    def _on_lifecycle(params: dict) -> None:
        events.append(params)
        arrived.set()

    async def _run() -> None:
        nonlocal phase
        result = await session.send("Page.navigate", {"url": url})
        if result.get("errorText"):
            raise NavigationError(url, result["errorText"])
        loader_id = result.get("loaderId")
        if event_name is not None and loader_id:
            phase = wait_until
            await wait_lifecycle(events, arrived, result.get("frameId"), loader_id, event_name)

    session.on("Page.lifecycleEvent", _on_lifecycle)
    try:
        await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError:
        await stop_loading(session)
        raise NavigationTimeoutError(url, phase, timeout, _dialog_hint(dialogs)) from None
    finally:
        session.off("Page.lifecycleEvent", _on_lifecycle)


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
    except asyncio.TimeoutError:
        raise NavigationTimeoutError(pattern or "any URL", phase, timeout) from None
    finally:
        session.off("Page.frameNavigated", _on_navigated)
        session.off("Page.lifecycleEvent", _on_lifecycle)
    return committed.get("url", "")


async def stop_loading(session: Session) -> None:
    """Best-effort ``Page.stopLoading`` after a navigation gave up."""
    try:
        await session.send("Page.stopLoading", {}, timeout=_SHORT_TIMEOUT)
    except Exception:  # noqa: BLE001 — the timeout error matters, not this
        logger.debug("Page.stopLoading failed", exc_info=True)


async def document_info(session: Session) -> tuple[str, str] | None:
    """Return ``(title, href)`` of the current document, or ``None`` if unreadable.

    Bounded: a page that stopped answering must not stall the navigation that
    just succeeded.
    """
    try:
        result = await session.send(
            "Runtime.evaluate",
            {"expression": "[document.title, location.href]", "returnByValue": True},
            timeout=_SHORT_TIMEOUT,
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

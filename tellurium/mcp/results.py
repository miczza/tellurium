"""Tool results: a short text plus ``structuredContent``, and errors turned
into a message that tells the agent what to do next."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from typing import Any

from mcp import types

from tellurium.browser.download import DownloadError
from tellurium.browser.geometry import ElementNotHittableError
from tellurium.browser.handles import StaleElementError
from tellurium.browser.launcher import LaunchError
from tellurium.browser.navigation import NavigationError
from tellurium.browser.snapshot import SnapshotTooLargeError
from tellurium.cdp.types import CDPError, TargetCrashedError
from tellurium.session.errors import SessionError


class ToolError(Exception):
    """A failure whose message is already written for the agent."""


@dataclass
class Reply:
    """What a tool hands back: *text* for the model, *data* as
    ``structuredContent``, an optional PNG *image*."""

    text: str
    data: dict[str, Any] | None = None
    image: bytes | None = None


def explain(exc: BaseException) -> str:
    """One message for *exc*: what went wrong and what the agent should do."""
    if isinstance(exc, ToolError):
        return str(exc)
    if isinstance(exc, StaleElementError):
        return _advise(f"Stale ref: {exc}", "The page changed: take a new snapshot")
    if isinstance(exc, ElementNotHittableError):
        return (
            f"Element covered, nothing was clicked: {exc}. Close the overlay, scroll, "
            "or take a new snapshot."
        )
    if isinstance(exc, SnapshotTooLargeError):
        return (
            f"Page too large to snapshot whole ({exc}): pass selector= (CSS of one part, "
            "e.g. 'form') or interactive=true."
        )
    if isinstance(exc, KeyError):  # a LookupError, but never a ref problem
        return f"KeyError: {exc}"
    if isinstance(exc, LookupError):
        if "ref" in str(exc).lower():
            return _advise(str(exc), "Refs come from the latest snapshot of this tab")
        return f"{exc}: check the CSS selector, or leave selector out"
    if isinstance(exc, CDPError):
        return _chrome_error(exc)
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return f"Timed out: {exc or 'the call took too long'}."
    if isinstance(exc, NavigationError):
        return f"Navigation failed: {exc}"
    if isinstance(exc, DownloadError):
        return f"Download failed: {exc}"
    if isinstance(exc, TargetCrashedError):
        return "The tab crashed: close it with tab-close and open a new one with tab-open."
    if isinstance(exc, ConnectionError):
        return f"The tab or its browser is gone ({exc}): see tab-list and session-list."
    if isinstance(exc, LaunchError):
        if "SingletonLock" in str(exc) or "ProcessSingleton" in str(exc):
            return (
                "This session is already open in another process (its profile is locked): "
                "close it there, or open another name."
            )
        return f"Chrome did not start: {exc}"
    if isinstance(exc, SessionError):
        return f"Session error: {exc}"
    return f"{type(exc).__name__}: {exc}"


def _advise(message: str, advice: str) -> str:
    """*message* plus *advice*, unless it already says to take a snapshot."""
    if "snapshot" in message.lower():
        return f"{message}."
    return f"{message}. {advice}."


def _chrome_error(exc: CDPError) -> str:
    if "not focusable" in exc.message:
        return (
            "That element cannot take keyboard focus: fill and press need a text field "
            "(textbox, searchbox, combobox) ref; click other elements instead."
        )
    if "invalid URL" in exc.message:
        return "Invalid URL: give a full address such as https://example.com/."
    return f"Chrome refused the command: {exc.message}"


def success(reply: Reply) -> types.CallToolResult:
    content: list[Any] = [types.TextContent(type="text", text=reply.text)]
    if reply.image is not None:
        data = base64.b64encode(reply.image).decode("ascii")
        content.append(types.ImageContent(type="image", data=data, mime_type="image/png"))
    return types.CallToolResult(content=content, structured_content=reply.data)


def failure(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)], is_error=True
    )

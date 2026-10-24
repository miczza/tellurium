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
from tellurium.cdp.types import TargetCrashedError
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
        return f"Stale ref: {exc}. The page changed: take a new snapshot and use its refs."
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
        return f"{exc}. Refs come from the latest snapshot of this tab."
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
        return f"Chrome did not start: {exc}"
    if isinstance(exc, SessionError):
        return f"Session error: {exc}"
    return f"{type(exc).__name__}: {exc}"


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

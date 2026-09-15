"""Fetch-based request interception for modification, blocking, and mocking.

More invasive than Network.enable — use only when you need to modify,
block, or respond to requests. Requires explicit continue_(), abort(),
or respond() for each paused request.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass


@dataclass
class InterceptedRequest:
    """A paused request awaiting user decision."""

    request_id: str
    url: str
    method: str
    headers: dict
    session: object  # CDP session for sending commands

    async def continue_(self, *, headers: dict | None = None) -> None:
        """Continue the request, optionally with modified headers."""
        params: dict = {"requestId": self.request_id}
        if headers is not None:
            # CDP expects [{name, value}, ...]
            params["headers"] = [{"name": k, "value": v} for k, v in headers.items()]
        await self.session.send("Fetch.continueRequest", params)

    async def abort(self) -> None:
        """Abort the request (block it)."""
        await self.session.send(
            "Fetch.failRequest",
            {
                "requestId": self.request_id,
                "errorReason": "Aborted",
            },
        )

    async def respond(
        self,
        status: int = 200,
        body: str = "",
        headers: dict | None = None,
    ) -> None:
        """Respond with a mock response (never hits the network)."""
        params: dict = {
            "requestId": self.request_id,
            "responseCode": status,
            "body": base64.b64encode(body.encode()).decode(),
        }
        if headers:
            params["responseHeaders"] = [{"name": k, "value": v} for k, v in headers.items()]
        await self.session.send("Fetch.fulfillRequest", params)


class InterceptStream:
    """Async iterator yielding InterceptedRequest objects.

    Usage:
        async with tab.intercept("*/api/*") as stream:
            async for request in stream:
                await request.continue_()
    """

    def __init__(self, session, url_pattern: str = "*"):
        self._session = session
        self._url_pattern = url_pattern
        self._queue: asyncio.Queue[InterceptedRequest] = asyncio.Queue()
        self._active = False

    async def start(self) -> None:
        """Enable Fetch interception."""
        await self._session.send(
            "Fetch.enable",
            {
                "patterns": [{"urlPattern": self._url_pattern}],
            },
        )
        self._session.on("Fetch.requestPaused", self._on_paused)
        self._active = True

    async def stop(self) -> None:
        """Disable Fetch interception."""
        if not self._active:
            return
        await self._session.send("Fetch.disable", {})
        self._session.off("Fetch.requestPaused", self._on_paused)
        self._active = False

    def _on_paused(self, params: dict) -> None:
        """Handle Fetch.requestPaused event."""
        req = InterceptedRequest(
            request_id=params["requestId"],
            url=params["request"]["url"],
            method=params["request"]["method"],
            headers=params["request"].get("headers", {}),
            session=self._session,
        )
        self._queue.put_nowait(req)

    def __aiter__(self):
        return self

    async def __anext__(self) -> InterceptedRequest:
        while True:
            if not self._active:
                raise StopAsyncIteration
            try:
                return await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
        return False

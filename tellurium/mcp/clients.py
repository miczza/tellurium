"""The browsers of each MCP client over HTTP: one :class:`SessionPool` per MCP
session (``Mcp-Session-Id``), so a client never sees another one's sessions or
tabs; named sessions stay shared on disk through one :class:`SessionClaims`.

A client's pool is closed (named sessions saved) when its MCP session ends,
after *idle_timeout* seconds without a tool call, and when the server stops.
A client that comes back after its idle timeout gets a new, empty pool.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from tellurium.mcp.claims import SessionClaims
from tellurium.mcp.config import DEFAULT_IDLE_TIMEOUT, ServerConfig
from tellurium.mcp.results import ToolError
from tellurium.mcp.sessions import SessionPool

logger = logging.getLogger(__name__)
# While a call runs, the watchdog looks again this often.
_BUSY_POLL = 5.0


@dataclass
class _Client:
    pool: SessionPool
    last: float
    active: int = 0
    watchdog: asyncio.Task | None = field(default=None, repr=False)


class ClientPools:
    """Owns the pool of every client; ``async with`` closes them all."""

    def __init__(self, config: ServerConfig, idle_timeout: float | None = DEFAULT_IDLE_TIMEOUT):
        self.config = config
        self.idle_timeout = idle_timeout or None
        self.claims = SessionClaims()
        self._clients: dict[str, _Client] = {}
        self._drops: dict[str, asyncio.Task] = {}
        self._closed = False

    async def __aenter__(self) -> ClientPools:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close_all()

    @asynccontextmanager
    async def use(self, client_id: str | None) -> AsyncIterator[SessionPool]:
        """The pool of client *client_id*, held for one tool call: a call in
        flight is never idleness."""
        if client_id is None:
            raise ToolError("This server needs an MCP session (Streamable HTTP, Mcp-Session-Id)")
        pending = self._drops.get(client_id)
        if pending is not None:  # its old pool still holds profiles: let it finish
            await asyncio.shield(pending)
        if self._closed:
            raise ToolError("The server is shutting down")
        client = self._clients.get(client_id) or self._add(client_id)
        client.active += 1
        try:
            yield client.pool
        finally:
            client.active -= 1
            client.last = asyncio.get_running_loop().time()

    def _add(self, client_id: str) -> _Client:
        pool = SessionPool(self.config, claims=self.claims)
        client = _Client(pool, last=asyncio.get_running_loop().time())
        if self.idle_timeout is not None:
            client.watchdog = asyncio.ensure_future(self._watch(client_id, client))
        self._clients[client_id] = client
        return client

    async def _watch(self, client_id: str, client: _Client) -> None:
        assert self.idle_timeout is not None
        loop = asyncio.get_running_loop()
        while True:
            left = client.last + self.idle_timeout - loop.time()
            if client.active:
                await asyncio.sleep(min(self.idle_timeout, _BUSY_POLL))
            elif left > 0:
                await asyncio.sleep(left)
            else:
                break
        if client.pool.sessions():
            logger.info(
                "client %s idle for %gs: closing its sessions", client_id, self.idle_timeout
            )
        self.forget(client_id)

    def forget(self, client_id: str) -> asyncio.Task | None:
        """Start closing (and saving) the pool of a client that went away, and
        return that close: a task the server owns, which no cancellation stops."""
        client = self._clients.pop(client_id, None)
        if client is None:
            return self._drops.get(client_id)
        if client.watchdog is not None and client.watchdog is not asyncio.current_task():
            client.watchdog.cancel()
        task = asyncio.ensure_future(client.pool.close_all())
        self._drops[client_id] = task

        def done(_: asyncio.Task) -> None:
            if self._drops.get(client_id) is task:
                del self._drops[client_id]

        task.add_done_callback(done)
        return task

    async def drop(self, client_id: str) -> None:
        """Close (and save) the pool of client *client_id*."""
        task = self.forget(client_id)
        if task is not None:
            await asyncio.shield(task)

    async def close_all(self) -> None:
        """Close every client's pool, saving named sessions; one failing does
        not stop the others (its pool logs it)."""
        self._closed = True
        for client_id in list(self._clients):
            self.forget(client_id)
        if self._drops:
            await asyncio.wait(set(self._drops.values()))

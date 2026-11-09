"""One HTTP connection of ``tellurium mcp --http``: uvicorn's h11 protocol with
deadlines on each request and a lingering close.

Deadlines: the head must arrive within HEADER_TIMEOUT, then the body within
BODY_TIMEOUT. uvicorn's own keep-alive timer stops at the first byte, so a
client dribbling headers or a body (slowloris) would otherwise hold a
connection forever, token or not.

Lingering close: when the server ends a connection whose client is still
sending a body (a refusal answered before the body was read, or a body cut at
its deadline), closing the socket at once makes the kernel answer the bytes
still coming with a reset. Windows and macOS then discard what the client has
not read yet, the refusal included. So the server half-closes instead (the
client reads the reply, then the end of stream), reads and drops what is still
coming, up to DRAIN_BYTES and for at most DRAIN_TIMEOUT, then closes. A
connection being drained no longer serves a request: the app sees the client
gone at once.
"""

from __future__ import annotations

import asyncio
from typing import Any

import h11
from uvicorn.protocols.http.h11_impl import H11Protocol

# A request head (line and headers) must arrive whole within this many seconds.
HEADER_TIMEOUT = 5.0
# Once the head is in, the body must follow whole within this many seconds.
BODY_TIMEOUT = 10.0
# After the server ended a connection mid-body, what it still reads and drops
# before closing: the end of a request body a client already had in flight.
DRAIN_TIMEOUT = 2.0
DRAIN_BYTES = 1024 * 1024


class _LingeringTransport:
    """The transport uvicorn sees: everything passes through but ``close``,
    which the connection turns into a lingering close when it has to."""

    def __init__(self, inner: asyncio.Transport, connection: GuardedConnection):
        self._inner = inner
        self._connection = connection

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def close(self) -> None:
        self._connection.end()

    def is_closing(self) -> bool:
        return self._connection.draining or self._inner.is_closing()


class GuardedConnection(H11Protocol):
    """uvicorn's h11 protocol with request deadlines and a lingering close."""

    def connection_made(self, transport: Any) -> None:
        self._socket = transport
        self.draining = False
        self._drain_left = 0  # bytes still accepted while draining
        self._drain_timer: asyncio.TimerHandle | None = None
        super().connection_made(_LingeringTransport(transport, self))
        self._timer = self.loop.call_later(HEADER_TIMEOUT, self._overdue, h11.IDLE)
        self._body_timed = False

    def end(self) -> None:
        """Close the connection; linger while the client is still sending a body."""
        if self.draining or self._socket.is_closing():
            return
        if self.conn.their_state is not h11.SEND_BODY or not self._socket.can_write_eof():
            self._socket.close()
            return
        self.draining = True
        self._drain_left = DRAIN_BYTES
        self._timer.cancel()
        self._drain_timer = self.loop.call_later(DRAIN_TIMEOUT, self._socket.close)
        if self.cycle is not None and not self.cycle.response_complete:
            # The request is over for the app too, as when the client leaves.
            self.cycle.disconnected = True
            self.cycle.message_event.set()
        self._socket.write_eof()  # after the reply already written
        self._socket.resume_reading()  # uvicorn may have paused it on a big body

    def data_received(self, data: bytes) -> None:
        if not self.draining:
            super().data_received(data)
            return
        self._drain_left -= len(data)
        if self._drain_left < 0:
            self._socket.close()
        # At the client's end of stream uvicorn's eof_received lets asyncio close.

    def handle_events(self) -> None:
        super().handle_events()
        if self.conn.their_state is h11.SEND_BODY and not self._body_timed:
            self._body_timed = True
            self._timer.cancel()
            self._timer = self.loop.call_later(BODY_TIMEOUT, self._overdue, h11.SEND_BODY)

    def on_response_complete(self) -> None:
        super().on_response_complete()
        self._timer.cancel()
        self._body_timed = False
        if not self.transport.is_closing():
            self._timer = self.loop.call_later(HEADER_TIMEOUT, self._overdue, h11.IDLE)

    def connection_lost(self, exc: Exception | None) -> None:
        self._timer.cancel()
        if self._drain_timer is not None:
            self._drain_timer.cancel()
        super().connection_lost(exc)

    def _overdue(self, waiting: type) -> None:
        # Still waiting for the same part of the request: the client is too slow.
        if self.conn.their_state is waiting and not self.transport.is_closing():
            self.transport.close()

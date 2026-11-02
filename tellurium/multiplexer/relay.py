"""Relay — one Chrome's CDP pipe and at most one WebSocket client on it.

The :class:`Relay` is the only reader of the pipe. It numbers every command
itself: a client's ``id`` is swapped for one of its own on the way in and
restored on the reply, so the client may reuse or scatter its ids and the
health probes sent on the same pipe never collide with them. Events, with or
without ``sessionId``, reach the client untouched; with no client they are
dropped. A client message that is not a JSON object with an integer ``id``
closes the connection with 1007. What Chrome sends waits in a bounded queue
for the client: a client that reads too slowly is disconnected (1008)
instead of growing the server's memory or stalling the pipe.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import deque
from typing import Any

#: Ids are drawn below this bound: ``RawChrome`` used ``2**31 - 2`` for its own probe.
_ID_LIMIT = 2**31 - 16

#: Messages and bytes that may wait for a slow client before it is disconnected.
MAX_QUEUED_MESSAGES = 4096
MAX_QUEUED_BYTES = 512 * 2**20

#: Commands of the client Chrome has not answered yet, at most.
MAX_PENDING = 16384

#: WebSocket close codes.
CLOSE_GOING_AWAY = 1001
CLOSE_BAD_DATA = 1007
CLOSE_POLICY = 1008
CLOSE_ERROR = 1011
CLOSE_NORMAL = 1000


class RelayClosed(Exception):
    """The pipe is gone: Chrome exited or the relay was closed."""


class Relay:
    """The pipe of one Chrome, with the id remapping and at most one client.

    :meth:`start` begins reading; :attr:`ended` resolves with a reason once the
    pipe breaks; :meth:`close` stops everything and disconnects the client.
    """

    def __init__(self, transport: Any) -> None:
        self._transport = transport
        self._next_id = 0
        #: own id -> the client's id, or the future of an internal probe
        self._pending: dict[int, int | asyncio.Future[dict]] = {}
        self._client: _Client | None = None
        self._reader: asyncio.Task | None = None
        self.ended: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        #: Whether the client asked Chrome to exit (``Browser.close``).
        self.closed_by_client = False

    def start(self) -> None:
        self._reader = asyncio.ensure_future(self._read())

    # ------------------------------------------------------------------ #
    # Chrome -> here
    # ------------------------------------------------------------------ #

    async def _read(self) -> None:
        try:
            while True:
                message = await self._transport.recv()
                self._dispatch(message)
        except (EOFError, ConnectionError, OSError, ValueError) as exc:
            self._end(f"Chrome closed its pipe ({type(exc).__name__})")
        except asyncio.CancelledError:
            self._end("the relay was closed")
            raise

    def _dispatch(self, message: dict) -> None:
        own = message.get("id")
        if own is None:
            if self._client is not None:
                self._client.push(message)
            return
        entry = self._pending.pop(own, None) if type(own) is int else None
        if entry is None:
            return  # a reply nobody waits for (a late probe, RawChrome's first)
        if isinstance(entry, asyncio.Future):
            if not entry.done():
                entry.set_result(message)
            return
        if self._client is not None:
            message["id"] = entry
            self._client.push(message)

    def _end(self, reason: str) -> None:
        if not self.ended.done():
            self.ended.set_result(reason)
        for entry in self._pending.values():
            if isinstance(entry, asyncio.Future) and not entry.done():
                entry.set_exception(RelayClosed(reason))
        self._pending.clear()

    # ------------------------------------------------------------------ #
    # here -> Chrome
    # ------------------------------------------------------------------ #

    def _own_id(self) -> int:
        while True:
            self._next_id = self._next_id % _ID_LIMIT + 1
            if self._next_id not in self._pending:
                return self._next_id

    async def _send(self, message: dict) -> None:
        if self.ended.done():
            raise RelayClosed(self.ended.result())
        data = json.dumps(message, separators=(",", ":")).encode() + b"\0"
        try:
            await self._transport.send(data)
        except (ConnectionError, OSError) as exc:
            self._end(f"Chrome closed its pipe ({type(exc).__name__})")
            raise RelayClosed(self.ended.result()) from exc

    async def probe(self, timeout: float) -> dict:
        """``Browser.getVersion`` on the pipe, answered within *timeout* seconds.

        Returns the ``result``; raises :class:`TimeoutError` when Chrome is
        silent and :class:`RelayClosed` when the pipe is gone. A late reply is
        dropped.
        """
        own = self._own_id()
        future: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
        self._pending[own] = future
        try:
            await self._send({"id": own, "method": "Browser.getVersion"})
            reply = await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Chrome did not answer within {timeout:g} s") from None
        finally:
            if self._pending.get(own) is future:
                del self._pending[own]
        return reply.get("result") or {}

    async def serve(self, ws: Any) -> None:
        """Relay between *ws* and Chrome until either side goes away.

        When the pipe breaks first the client is closed with 1011 and the
        reason (1000 if it had asked Chrome to close).
        """
        if self._client is not None:
            raise RuntimeError("this Chrome already has a client")
        client = self._client = _Client(ws)
        writer = asyncio.ensure_future(client.write())
        pump = asyncio.ensure_future(self._pump(ws))
        try:
            await asyncio.wait([pump, self.ended], return_when=asyncio.FIRST_COMPLETED)
            if self.ended.done():
                if self.closed_by_client:
                    await client.close(CLOSE_NORMAL, "Chrome closed by the client")
                else:
                    await client.close(CLOSE_ERROR, f"Chrome exited: {self.ended.result()}")
        finally:
            self._client = None
            for task in (pump, writer):
                task.cancel()
            await asyncio.wait([pump, writer])
            if not pump.cancelled() and pump.exception() is not None:
                raise pump.exception()

    async def _pump(self, ws: Any) -> None:
        """The client's commands to Chrome, with ids of the relay."""
        try:
            async for raw in ws:
                command = _command(raw)
                if command is None:
                    await ws.close(
                        CLOSE_BAD_DATA, "each message must be a JSON object with an integer id"
                    )
                    return
                if len(self._pending) >= MAX_PENDING:
                    await ws.close(CLOSE_POLICY, "too many commands waiting for Chrome")
                    return
                if command.get("method") == "Browser.close":
                    self.closed_by_client = True
                own = self._own_id()
                self._pending[own] = command["id"]
                command["id"] = own
                try:
                    await self._send(command)
                except RelayClosed:
                    return  # serve() closes the client with the reason
        except Exception as exc:  # noqa: BLE001 - the client went away: nothing to relay
            if not _is_closed(exc):
                raise

    async def disconnect(self, code: int, reason: str) -> None:
        """Close the client's WebSocket, if any, with *code* and *reason*."""
        client = self._client
        if client is not None:
            await client.close(code, reason)

    async def close(self, code: int = CLOSE_GOING_AWAY, reason: str = "") -> None:
        """Disconnect the client (*code*, *reason*) and stop reading the pipe."""
        try:
            await self.disconnect(code, reason)
        finally:
            reader, self._reader = self._reader, None
            if reader is not None:
                reader.cancel()
                await asyncio.wait([reader])
            self._end("the relay was closed")


def _command(raw: str | bytes) -> dict | None:
    """The client's message as a dict with an integer id, or None."""
    try:
        command = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(command, dict) or type(command.get("id")) is not int:
        return None
    return command


def _is_closed(exc: BaseException) -> bool:
    """Whether *exc* only says the WebSocket is closed."""
    from websockets.exceptions import ConnectionClosed

    return isinstance(exc, ConnectionClosed)


class _Client:
    """The WebSocket of the client and the bounded queue of what goes to it."""

    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self._queue: deque[str] = deque()
        self._bytes = 0
        self._ready = asyncio.Event()
        self._closing: asyncio.Task | None = None

    def push(self, message: dict) -> None:
        if self._closing is not None:
            return
        text = json.dumps(message, separators=(",", ":"))
        self._queue.append(text)
        self._bytes += len(text)
        if len(self._queue) > MAX_QUEUED_MESSAGES or self._bytes > MAX_QUEUED_BYTES:
            self._queue.clear()
            self._bytes = 0
            self._closing = asyncio.ensure_future(
                self._ws.close(CLOSE_POLICY, "the client reads too slowly")
            )
            return
        self._ready.set()

    async def write(self) -> None:
        try:
            while True:
                await self._ready.wait()
                while self._queue:
                    text = self._queue.popleft()
                    self._bytes -= len(text)
                    await self._ws.send(text)
                self._ready.clear()
        except Exception as exc:  # noqa: BLE001 - the client went away
            if not _is_closed(exc):
                raise
        finally:
            if self._closing is not None:
                with contextlib.suppress(Exception):
                    await self._closing

    async def close(self, code: int, reason: str) -> None:
        with contextlib.suppress(Exception):
            await self._ws.close(code, reason[:120])

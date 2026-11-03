"""Relay — one Chrome's CDP pipe and at most one WebSocket client on it.

The :class:`Relay` is the only reader of the pipe. It numbers every command
itself: a client's ``id`` is swapped for one of its own on the way in and
restored on the reply, so the client may reuse or scatter its ids and the
health probes sent on the same pipe never collide with them. Events, with or
without ``sessionId``, reach the client untouched; with no client they are
dropped. A client message that is not a JSON object with an integer ``id``
closes the connection with 1007.

The relay may keep sessions of its own on the pipe, kept from the client by
:class:`~tellurium.multiplexer.own_session.OwnSessions` (see there).

Both ways are bounded in bytes, by back-pressure rather than by closing:
past :data:`HIGH_WATER` bytes waiting for the client the relay stops reading
the pipe (Chrome keeps the rest, as it does for a slow WebSocket client of
its own) until the client catches up; past :data:`MAX_INFLIGHT_BYTES` of
commands Chrome has not answered it stops reading the client. Only a client
that takes nothing for :data:`STALL_LIMIT` seconds is closed (1008).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import deque
from typing import Any

from tellurium.multiplexer.own_session import CommandError, OwnSessions

#: Ids are drawn below this bound: ``RawChrome`` used ``2**31 - 2`` for its own probe.
_ID_LIMIT = 2**31 - 16

#: Bytes waiting for the client above which the pipe is no longer read. Messages
#: are JSON with ``ensure_ascii``: one character is one byte.
HIGH_WATER = 16 * 2**20
#: Seconds a client that holds the pipe up may go without taking a message.
STALL_LIMIT = 60.0

#: Bytes of client commands Chrome has not answered above which the client is no
#: longer read (one command alone may be larger), and their number.
MAX_INFLIGHT_BYTES = 64 * 2**20
MAX_PENDING = 16384

#: Seconds a closing handshake with a client may take; then its socket is cut.
#: A client that reads nothing would otherwise hold ``close()`` in ``drain()``.
CLOSE_WAIT = 5.0

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
        #: own id -> (the client's id, the command's size), or the future of a probe
        self._pending: dict[int, tuple[int, int] | asyncio.Future[dict]] = {}
        self._inflight = 0  # commands of the client in _pending
        self._inflight_bytes = 0
        self._answered = asyncio.Event()  # a reply to the client came (or the pipe ended)
        #: True while the pipe is not read because the client is behind; *pauses*
        #: counts those spells, so a probe that spans one is not a hang.
        self.paused = False
        self.pauses = 0
        #: Messages read from the pipe so far: Chrome that speaks is alive.
        self.received = 0
        self._client: _Client | None = None
        self._reader: asyncio.Task | None = None
        self.ended: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        #: Whether the client asked Chrome to exit (``Browser.close``).
        self.closed_by_client = False
        #: The relay's own sessions, kept from the client.
        self.own = OwnSessions()

    def start(self) -> None:
        self._reader = asyncio.ensure_future(self._read())

    # ------------------------------------------------------------------ #
    # Chrome -> here
    # ------------------------------------------------------------------ #

    async def _read(self) -> None:
        try:
            while True:
                client = self._client
                if client is not None and client.queued > HIGH_WATER:
                    await self._wait_for(client)
                message = await self._transport.recv()
                self.received += 1
                self._dispatch(message)
        except (EOFError, ConnectionError, OSError, ValueError) as exc:
            self._end(f"Chrome closed its pipe ({type(exc).__name__})")
        except asyncio.CancelledError:
            self._end("the relay was closed")
            raise

    async def _wait_for(self, client: _Client) -> None:
        """Leave Chrome's messages in the pipe until *client* catches up; close it
        (1008) if it takes nothing for :data:`STALL_LIMIT` seconds."""
        loop = asyncio.get_running_loop()
        self.paused, self.pauses = True, self.pauses + 1
        start = loop.time()
        try:
            while client.queued > HIGH_WATER and self._client is client:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(client.room.wait(), 1.0)
                if loop.time() - max(start, client.last_sent) > STALL_LIMIT:
                    client.abandon(CLOSE_POLICY, f"the client took nothing for {STALL_LIMIT:g} s")
                    return
        finally:
            self.paused = False

    def _dispatch(self, message: dict) -> None:
        own = message.get("id")
        if own is None:
            if not self.own.take(message):
                self._deliver(message)
            return
        entry = self._pending.pop(own, None) if type(own) is int else None
        if entry is None:
            return  # a reply nobody waits for (a late probe, RawChrome's first)
        if isinstance(entry, asyncio.Future):
            if not entry.done():
                entry.set_result(message)
            return
        client_id, size = entry
        self._inflight -= 1
        self._inflight_bytes -= size
        self._answered.set()
        message["id"] = client_id
        self._deliver(message)

    def _deliver(self, message: dict) -> None:
        """*message* to the client, if any (held while an own session attaches)."""
        if self.own.holding:
            self.own.hold(message)
        elif self._client is not None:
            self._client.push(message)

    def release_held(self) -> None:
        """An own attach is over: what was held goes to the client, in order."""
        for message in self.own.end_attach():
            self._deliver(message)

    def _end(self, reason: str) -> None:
        if not self.ended.done():
            self.ended.set_result(reason)
        for entry in self._pending.values():
            if isinstance(entry, asyncio.Future) and not entry.done():
                entry.set_exception(RelayClosed(reason))
        self._pending.clear()
        self._inflight = self._inflight_bytes = 0
        self._answered.set()

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
        reply = await self._ask({"method": "Browser.getVersion"}, timeout)
        return reply.get("result") or {}

    async def call(
        self,
        method: str,
        params: dict | None = None,
        *,
        timeout: float,
        session_id: str | None = None,
    ) -> dict:
        """A command of the relay's own (on *session_id*, else the root): its
        ``result``. Raises as :meth:`probe` does, and :class:`CommandError`
        when Chrome answers with an error. The reply never reaches the client."""
        command: dict[str, Any] = {"method": method, "params": params or {}}
        if session_id is not None:
            command["sessionId"] = session_id
        reply = await self._ask(command, timeout)
        error = reply.get("error")
        if error is not None:
            message = error.get("message") if isinstance(error, dict) else error
            raise CommandError(f"{method}: {message}")
        return reply.get("result") or {}

    async def _ask(self, command: dict, timeout: float) -> dict:
        own = self._own_id()
        future: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
        self._pending[own] = future
        try:
            await self._send({"id": own, **command})
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            raise TimeoutError(f"Chrome did not answer within {timeout:g} s") from None
        finally:
            if self._pending.get(own) is future:
                del self._pending[own]

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
        # The pump may be held back by commands Chrome has not answered: the
        # client leaving must end the relay all the same.
        gone = asyncio.ensure_future(ws.wait_closed())
        try:
            await asyncio.wait([pump, gone, self.ended], return_when=asyncio.FIRST_COMPLETED)
            if self.ended.done():
                if self.closed_by_client:
                    await client.close(CLOSE_NORMAL, "Chrome closed by the client")
                else:
                    await client.close(CLOSE_ERROR, f"Chrome exited: {self.ended.result()}")
        finally:
            self._client = None
            for task in (pump, writer, gone):
                task.cancel()
            await asyncio.wait([pump, writer, gone])
            if not pump.cancelled() and pump.exception() is not None:
                raise pump.exception()

    async def _pump(self, ws: Any) -> None:
        """The client's commands to Chrome, with ids of the relay."""
        try:
            async for raw in ws:
                command = _command(raw)
                if command is None:
                    await close_client(
                        ws, CLOSE_BAD_DATA, "each message must be a JSON object with an integer id"
                    )
                    return
                refusal = self.own.refusal(command)
                if refusal is not None:
                    self._deliver(refusal)  # Chrome never sees it
                    continue
                size = len(raw)
                while self._inflight and (
                    self._inflight >= MAX_PENDING
                    or self._inflight_bytes + size > MAX_INFLIGHT_BYTES
                ):
                    if self.ended.done():
                        return  # serve() closes the client with the reason
                    self._answered.clear()
                    await self._answered.wait()  # Chrome answers: room again
                if command.get("method") == "Browser.close":
                    self.closed_by_client = True
                own = self._own_id()
                self._pending[own] = (command["id"], size)
                self._inflight += 1
                self._inflight_bytes += size
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
    except (ValueError, RecursionError):  # RecursionError: nested beyond Python's stack
        return None
    if not isinstance(command, dict) or type(command.get("id")) is not int:
        return None
    return command


async def close_client(ws: Any, code: int, reason: str) -> None:
    """Close *ws* with *code* and *reason*, within :data:`CLOSE_WAIT` seconds:
    past it (a client that reads nothing), its socket is cut."""
    try:
        await asyncio.wait_for(ws.close(code, reason[:120]), CLOSE_WAIT)
    except Exception:  # noqa: BLE001 - timed out or already broken: cut it below
        pass
    finally:
        # transport.close() waits to flush what the client never reads: abort.
        transport = getattr(ws, "transport", None)
        if transport is not None and (not transport.is_closing() or _still_open(ws)):
            transport.abort()


def _still_open(ws: Any) -> bool:
    """Whether the closing handshake of *ws* has not ended (its socket still up)."""
    waiter = getattr(ws, "connection_lost_waiter", None)
    return waiter is not None and not waiter.done()


def _is_closed(exc: BaseException) -> bool:
    """Whether *exc* only says the WebSocket is closed."""
    from websockets.exceptions import ConnectionClosed

    return isinstance(exc, ConnectionClosed)


class _Client:
    """The WebSocket of the client and what waits to go to it."""

    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self._queue: deque[str] = deque()
        self.queued = 0  # bytes in the queue
        self._ready = asyncio.Event()
        #: Set while the queue is at or below HIGH_WATER.
        self.room = asyncio.Event()
        self.room.set()
        self.last_sent = 0.0  # loop time of the last message the client took
        self._closing: asyncio.Task | None = None

    def push(self, message: dict) -> None:
        if self._closing is not None:
            return
        text = json.dumps(message, separators=(",", ":"), ensure_ascii=True)
        self._queue.append(text)
        self.queued += len(text)
        if self.queued > HIGH_WATER:
            self.room.clear()
        self._ready.set()

    def abandon(self, code: int, reason: str) -> None:
        """Drop what waits and close the client."""
        self._queue.clear()
        self.queued = 0
        self.room.set()
        if self._closing is None:
            self._closing = asyncio.ensure_future(close_client(self._ws, code, reason))

    async def write(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while True:
                await self._ready.wait()
                while self._queue:
                    text = self._queue.popleft()
                    await self._ws.send(text)
                    self.queued -= len(text)
                    self.last_sent = loop.time()
                    if self.queued <= HIGH_WATER:
                        self.room.set()
                self._ready.clear()
        except Exception as exc:  # noqa: BLE001 - the client went away
            if not _is_closed(exc):
                raise
        finally:
            if self._closing is not None:
                with contextlib.suppress(Exception):
                    await self._closing

    async def close(self, code: int, reason: str) -> None:
        await close_client(self._ws, code, reason)

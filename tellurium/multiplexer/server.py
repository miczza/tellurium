"""Server — the multiplexer's HTTP and WebSocket endpoint, as Chrome's would be.

``GET /json/version`` (and ``/json/version/``) answers like Chrome's, with
the values of a real ``Browser.getVersion`` and a ``webSocketDebuggerUrl``;
a WebSocket upgrade on ``/devtools/browser/<anything>`` takes a place of the
pool (in the queue up to its timeout, else HTTP 503) and relays the client to
a Chrome of its own. Every request, upgrade included, passes the same checks
first: no repeated access header, a ``Host`` naming the bind address, no
``Origin`` (CDP clients send none, web pages always do), no token in the URL
(query or path, even percent-encoded twice), then ``Authorization: Bearer``.
The ``/admin`` routes (:mod:`.admin`) come after the same checks. A request
with a body (none of these takes one) gets 400 before any of them.
"""

from __future__ import annotations

import asyncio
import contextlib
import http
import json
import re
import uuid
from typing import Any

from tellurium.access import (
    allowed_hosts,
    bearer_ok,
    host_ok,
    repeated_header,
    token_leaked,
)
from tellurium.multiplexer import pool as pool_module
from tellurium.multiplexer.admin import Admin, is_admin
from tellurium.multiplexer.pool import ClientGone, NoChrome, Pool, PoolClosed, QueueTimeout
from tellurium.multiplexer.relay import close_client

#: Largest WebSocket message either way (full-page screenshots, response bodies).
MAX_MESSAGE = 256 * 2**20
#: Frames read ahead from a client before the server stops reading its socket.
MAX_FRAMES = 16
#: Seconds the closing handshake with a client may take.
CLOSE_TIMEOUT = 5.0
#: Seconds a new connection has to send its request, before it is dropped.
REQUEST_TIMEOUT = 10.0
#: Connections whose request has not come yet, at most: past it the oldest is
#: dropped, so silent sockets cannot use up the descriptors (or crowd out a
#: client with the token, whose request comes at once).
MAX_UNCHECKED = 64

_VERSION_PATHS = frozenset({"/json/version", "/json/version/"})
_BROWSER_PATH = re.compile(r"/devtools/browser/[^/?#]*")
_WEBKIT = re.compile(r"AppleWebKit/([\d.]+)")
_INSTALL = "the multiplexer needs websockets>=17: pip install 'tellurium[multiplex]'"


def require_websockets() -> Any:
    """``websockets.asyncio.server``, or ImportError with the install line."""
    try:
        from websockets.asyncio import server
    except ImportError:
        raise ImportError(_INSTALL) from None
    return server


class Server:
    """The listening socket and its connections, for one :class:`Pool`."""

    def __init__(
        self, pool: Pool, token: str, host: str, port: int, admin: Admin | None = None
    ) -> None:
        self._pool = pool
        self._admin = admin
        self._token = token
        self._host = host
        self._port = port
        self._hosts = allowed_hosts(host)
        self._browser_id = str(uuid.uuid4())
        self._server: Any = None
        self._leases: dict[Any, Any] = {}
        self._orphans: set[asyncio.Task] = set()
        #: WebSocket connections being relayed (closed by us on shutdown)
        self._active: set[Any] = set()
        self._open: set[Any] = set()  # every connection, from accept to loss
        #: connection -> the timer that drops it if its request does not come
        self._unchecked: dict[Any, asyncio.TimerHandle] = {}
        self.port: int | None = None

    async def start(self) -> None:
        server = require_websockets()
        self._server = await server.serve(
            self._handle,
            self._host,
            self._port,
            process_request=self._process_request,
            max_size=MAX_MESSAGE,
            max_queue=MAX_FRAMES,
            open_timeout=None,  # REQUEST_TIMEOUT before the checks; the queue has its own
            create_connection=self._connection_class(server.ServerConnection),
            close_timeout=CLOSE_TIMEOUT,
            ping_interval=None,
            compression=None,
            server_header=None,
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        """Stop listening, close the clients with 1001, release every lease."""
        if self._server is not None:
            server, self._server = self._server, None
            # Ours first, bounded: websockets' own close would wait on a client
            # that reads nothing. Then no new connection, and the handlers end.
            await asyncio.gather(
                *(close_client(c, 1001, "the multiplexer is shutting down") for c in self._active)
            )
            server.close()
            try:
                await asyncio.wait_for(server.wait_closed(), CLOSE_TIMEOUT * 3)
            except TimeoutError:
                for connection in list(self._open):
                    connection.transport.abort()
                await server.wait_closed()
        await asyncio.sleep(0)  # done callbacks of the last handshakes
        while self._orphans:
            await asyncio.wait(list(self._orphans))
        for timer in self._unchecked.values():
            timer.cancel()
        self._unchecked.clear()

    # ------------------------------------------------------------------ #
    # Connections before their request
    # ------------------------------------------------------------------ #

    def _connection_class(self, base: type) -> type:
        guard = self

        class GuardedConnection(base):  # type: ignore[misc, valid-type]
            def __init__(self, protocol: Any, *args: Any, **kwargs: Any) -> None:
                super().__init__(protocol, *args, **kwargs)
                _answer_bodies(protocol)

            def connection_made(self, transport: Any) -> None:
                super().connection_made(transport)
                guard._opened(self)

            def connection_lost(self, exc: Exception | None) -> None:
                try:
                    super().connection_lost(exc)
                finally:
                    guard._checked(self)
                    guard._open.discard(self)

        return GuardedConnection

    def _opened(self, connection: Any) -> None:
        self._open.add(connection)
        while len(self._unchecked) >= MAX_UNCHECKED:
            oldest = next(iter(self._unchecked))
            self._checked(oldest)
            oldest.transport.abort()
        loop = asyncio.get_running_loop()
        self._unchecked[connection] = loop.call_later(REQUEST_TIMEOUT, self._expire, connection)

    def _expire(self, connection: Any) -> None:
        if self._unchecked.pop(connection, None) is not None:
            connection.transport.abort()

    def _checked(self, connection: Any) -> None:
        timer = self._unchecked.pop(connection, None)
        if timer is not None:
            timer.cancel()

    # ------------------------------------------------------------------ #
    # HTTP, before any upgrade
    # ------------------------------------------------------------------ #

    async def _process_request(self, connection: Any, request: Any) -> Any:
        self._checked(connection)  # its request came: no longer at risk of the timer
        refusal = self._refusal(request)
        if refusal is not None:
            return _reply(connection, *refusal)
        path = request.path.partition("?")[0]
        method = request.method
        if is_admin(path):
            if self._admin is None:
                return _reply(connection, 404, "Not found: no administration here")
            answer = self._admin.answer(method, path)
            return _reply(
                connection, answer.status, answer.body, answer.headers, json_body=answer.json_body
            )
        if method != "GET":
            return _reply(connection, 405, "Method Not Allowed: use GET", {"Allow": "GET"})
        if path in _VERSION_PATHS:
            return await self._version(connection, request)
        if not _BROWSER_PATH.fullmatch(path):
            return _reply(connection, 404, "Not found: connect to /devtools/browser/<id>")
        upgrade = [v for k, v in request.headers.raw_items() if k.lower() == "upgrade"]
        if [v.lower() for v in upgrade] != ["websocket"]:
            return _reply(connection, 426, "Upgrade Required: this path speaks WebSocket")
        try:
            lease = await self._pool.acquire(
                gone=getattr(connection, "connection_lost_waiter", None)
            )
        except (QueueTimeout, NoChrome, PoolClosed, ClientGone) as exc:
            return _reply(connection, 503, f"Service Unavailable: {exc}")
        self._leases[connection] = lease
        # The handler takes the lease; if the handshake fails it never runs.
        task = asyncio.current_task()
        assert task is not None
        task.add_done_callback(lambda _: self._drop(connection))
        return None

    def _refusal(self, request: Any) -> tuple[int, str, dict[str, str]] | None:
        repeated = repeated_header((name for name, _ in request.headers.raw_items()), ("upgrade",))
        if repeated:
            return 400, f"Header {repeated} sent more than once", {}
        headers = {name.lower(): value for name, value in request.headers.raw_items()}
        if not host_ok(headers, self._hosts, self.port or self._port):
            return 403, "Host not allowed (this server answers only on its bind address)", {}
        if "origin" in headers:
            return 403, "Requests from web pages are refused: CDP clients send no Origin", {}
        if token_leaked(request.path, self._token):
            return 400, "Never put the token in the URL: send it in the Authorization header", {}
        if not bearer_ok(headers, self._token):
            return (
                401,
                "Missing or wrong token: send 'Authorization: Bearer <token>' "
                "(the token is in the multiplex-token file of the server's home)",
                {"WWW-Authenticate": "Bearer"},
            )
        return None

    async def _version(self, connection: Any, request: Any) -> Any:
        try:
            version = await self._pool.browser_version(pool_module.LAUNCH_WAIT)
        except (TimeoutError, PoolClosed) as exc:
            return _reply(connection, 503, f"Service Unavailable: {exc}")
        host = request.headers.get("Host") or f"{self._host}:{self.port}"
        agent = version.get("userAgent", "")
        webkit = _WEBKIT.search(agent)
        revision = version.get("revision", "")
        body = {
            "Browser": version.get("product", ""),
            "Protocol-Version": version.get("protocolVersion", ""),
            "User-Agent": agent,
            "V8-Version": version.get("jsVersion", ""),
            "WebKit-Version": f"{webkit.group(1) if webkit else ''} ({revision})",
            "webSocketDebuggerUrl": f"ws://{host}/devtools/browser/{self._browser_id}",
        }
        return _reply(connection, 200, json.dumps(body, indent=3), json_body=True)

    def _drop(self, connection: Any) -> None:
        lease = self._leases.pop(connection, None)
        if lease is not None:
            task = asyncio.ensure_future(lease.release())
            self._orphans.add(task)
            task.add_done_callback(self._orphans.discard)

    # ------------------------------------------------------------------ #
    # WebSocket
    # ------------------------------------------------------------------ #

    async def _handle(self, connection: Any) -> None:
        lease = self._leases.pop(connection, None)
        if lease is None:
            await close_client(connection, 1011, "no Chrome was reserved for this connection")
            return
        self._active.add(connection)
        try:
            await lease.relay.serve(connection)
        finally:
            self._active.discard(connection)
            release = asyncio.ensure_future(lease.release())
            try:
                await asyncio.shield(release)
            except asyncio.CancelledError:
                with contextlib.suppress(BaseException):
                    await release
                raise

    @property
    def browser_id(self) -> str:
        return self._browser_id


def _answer_bodies(protocol: Any) -> None:
    """websockets reads no request body: it drops a request with one (any
    ``Content-Length`` but 0, or a ``Transfer-Encoding``) and closes without a
    word. Have it answer 400 first, before the EOF it sends."""
    send_eof = protocol.send_eof

    def answered_send_eof() -> None:
        if _has_body(protocol.handshake_exc):
            text = "Bad Request: a request with a body is not supported here\n"
            protocol.writes.append(protocol.reject(http.HTTPStatus.BAD_REQUEST, text).serialize())
        send_eof()

    protocol.send_eof = answered_send_eof


def _has_body(exc: BaseException | None) -> bool:
    """Whether *exc* is websockets' refusal of a request body."""
    cause = exc.__cause__ if exc is not None else None
    return isinstance(cause, NotImplementedError) or (
        isinstance(cause, ValueError) and str(cause) == "unsupported request body"
    )


def _reply(
    connection: Any,
    status: int,
    body: str,
    headers: dict[str, str] | None = None,
    *,
    json_body: bool = False,
) -> Any:
    response = connection.respond(http.HTTPStatus(status), body + "\n")
    if json_body:
        response.headers["Content-Type"] = "application/json; charset=UTF-8"
    for name, value in (headers or {}).items():
        response.headers[name] = value
    return response

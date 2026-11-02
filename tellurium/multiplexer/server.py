"""Server — the multiplexer's HTTP and WebSocket endpoint, as Chrome's would be.

``GET /json/version`` (and ``/json/version/``) answers like Chrome's, with
the values of a real ``Browser.getVersion`` and a ``webSocketDebuggerUrl``;
a WebSocket upgrade on ``/devtools/browser/<anything>`` takes a place of the
pool (in the queue up to its timeout, else HTTP 503) and relays the client to
a Chrome of its own. Every request, upgrade included, passes the same checks
first: no repeated access header, a ``Host`` naming the bind address, no
``Origin`` (CDP clients send none, web pages always do), no token in the URL
(query or path, even percent-encoded twice), then ``Authorization: Bearer``.
"""

from __future__ import annotations

import asyncio
import contextlib
import http
import ipaddress
import json
import re
import socket
import uuid
from typing import Any
from urllib.parse import unquote

from tellurium.access import (
    allowed_hosts,
    bearer_ok,
    host_ok,
    is_loopback,
    repeated_header,
    token_in_url,
)
from tellurium.multiplexer.pool import LAUNCH_WAIT, NoChrome, Pool, PoolClosed, QueueTimeout

#: Largest WebSocket message either way (full-page screenshots, response bodies).
MAX_MESSAGE = 256 * 2**20
#: Frames read ahead from a client before the server stops reading its socket.
MAX_FRAMES = 16
#: Seconds the closing handshake with a client may take.
CLOSE_TIMEOUT = 5.0

_VERSION_PATHS = frozenset({"/json/version", "/json/version/"})
_BROWSER_PATH = re.compile(r"/devtools/browser/[^/?#]*")
_WEBKIT = re.compile(r"AppleWebKit/([\d.]+)")
_INSTALL = "the multiplexer needs websockets>=13: pip install 'tellurium[multiplex]'"


def require_websockets() -> Any:
    """``websockets.asyncio.server``, or ImportError with the install line."""
    try:
        from websockets.asyncio import server
    except ImportError:
        raise ImportError(_INSTALL) from None
    return server


def host_names(bind: str) -> frozenset[str] | None:
    """The ``Host`` names allowed for a server bound to *bind*; None for a wildcard.

    Unlike :func:`~tellurium.access.allowed_hosts` alone, every spelling of a
    wildcard (``0``, ``::0``, ``0.0.0.0``) is one, and a loopback address
    other than 127.0.0.1 accepts its own name too.
    """
    address = _address(bind)
    if address is None:
        return allowed_hosts(bind)
    if address.is_unspecified:
        return None
    name = f"[{address}]" if address.version == 6 else str(address)
    if is_loopback(str(address)):
        return allowed_hosts("127.0.0.1") | {name}
    return frozenset({name})


def _address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    host = host.strip("[]")
    if host == "":
        return ipaddress.IPv4Address("0.0.0.0")
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:  # the short forms the system accepts: "0", "127.1"
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except OSError:
        return None


def token_leaked(target: str, token: str) -> bool:
    """Whether the request target (path and query) carries *token*: in the
    path, the query, or a usual token key, raw or percent-encoded up to twice."""
    path, _, query = target.partition("?")
    seen = target
    for _ in range(3):
        if token in seen:
            return True
        seen = unquote(seen)
    return token_in_url(query, token) or token_in_url(unquote(query), token)


class Server:
    """The listening socket and its connections, for one :class:`Pool`."""

    def __init__(self, pool: Pool, token: str, host: str, port: int) -> None:
        self._pool = pool
        self._token = token
        self._host = host
        self._port = port
        self._hosts = host_names(host)
        self._browser_id = str(uuid.uuid4())
        self._server: Any = None
        self._leases: dict[Any, Any] = {}
        self._orphans: set[asyncio.Task] = set()
        self.port: int | None = None

    async def start(self) -> None:
        server = require_websockets()
        open_timeout = self._pool.acquire_timeout + LAUNCH_WAIT + 10
        self._server = await server.serve(
            self._handle,
            self._host,
            self._port,
            process_request=self._process_request,
            max_size=MAX_MESSAGE,
            max_queue=MAX_FRAMES,
            open_timeout=open_timeout,
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
            server.close(code=1001, reason="the multiplexer is shutting down")
            await server.wait_closed()
        await asyncio.sleep(0)  # done callbacks of the last handshakes
        while self._orphans:
            await asyncio.wait(list(self._orphans))

    # ------------------------------------------------------------------ #
    # HTTP, before any upgrade
    # ------------------------------------------------------------------ #

    async def _process_request(self, connection: Any, request: Any) -> Any:
        refusal = self._refusal(request)
        if refusal is not None:
            return _reply(connection, *refusal)
        path = request.path.partition("?")[0]
        if path in _VERSION_PATHS:
            return await self._version(connection, request)
        if not _BROWSER_PATH.fullmatch(path):
            return _reply(connection, 404, "Not found: connect to /devtools/browser/<id>")
        if request.headers.get("Upgrade", "").lower() != "websocket":
            return _reply(connection, 426, "Upgrade Required: this path speaks WebSocket")
        try:
            lease = await self._pool.acquire()
        except (QueueTimeout, NoChrome, PoolClosed) as exc:
            return _reply(connection, 503, f"Service Unavailable: {exc}")
        self._leases[connection] = lease
        # The handler takes the lease; if the handshake fails it never runs.
        task = asyncio.current_task()
        assert task is not None
        task.add_done_callback(lambda _: self._drop(connection))
        return None

    def _refusal(self, request: Any) -> tuple[int, str, dict[str, str]] | None:
        repeated = repeated_header(name for name, _ in request.headers.raw_items())
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
            version = await self._pool.browser_version(LAUNCH_WAIT)
        except (TimeoutError, PoolClosed) as exc:
            return _reply(connection, 503, f"Service Unavailable: {exc}")
        host = request.headers.get("Host") or f"{self._host}:{self.port}"
        agent = version.get("userAgent", "")
        webkit = _WEBKIT.search(agent)
        body = {
            "Browser": version.get("product", ""),
            "Protocol-Version": version.get("protocolVersion", ""),
            "User-Agent": agent,
            "V8-Version": version.get("jsVersion", ""),
            "WebKit-Version": f"{webkit.group(1) if webkit else ''} ({version.get('revision', '')})",
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
            await connection.close(1011, "no Chrome was reserved for this connection")
            return
        try:
            await lease.relay.serve(connection)
        finally:
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

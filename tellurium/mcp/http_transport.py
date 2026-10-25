"""``tellurium mcp --http``: Streamable HTTP (the SDK's session manager under
uvicorn) behind the checks of :mod:`tellurium.mcp.auth`, with one session pool
per MCP client (:class:`ClientPools`).

Only handshake-era protocol versions are served: they carry an MCP session
(``Mcp-Session-Id``), which is what ties a client to its own browsers. A
request in the stateless 2026 envelope is answered with the versions we speak,
and clients fall back to the ``initialize`` handshake.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import sys
from collections.abc import Iterator
from typing import Any

import h11
import uvicorn
from mcp.server.streamable_http import MCP_SESSION_ID_HEADER
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp_types import INVALID_REQUEST, UNSUPPORTED_PROTOCOL_VERSION, ErrorData, JSONRPCError
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS
from starlette.datastructures import Headers
from uvicorn.protocols.http.h11_impl import H11Protocol

from tellurium.mcp import auth
from tellurium.mcp.clients import ClientPools
from tellurium.mcp.config import HttpConfig, ServerConfig
from tellurium.mcp.server import StartupError, build_server, build_tools

logger = logging.getLogger(__name__)

# How long open connections (a client's event stream) get to finish at shutdown.
SHUTDOWN_GRACE = 3.0
# A request head (line and headers) must arrive whole within this many seconds.
HEADER_TIMEOUT = 5.0
# Once the head is in, the body must follow whole within this many seconds.
BODY_TIMEOUT = 10.0
# Connections and requests served at once; more get 503 (MCP clients keep a few each).
CONCURRENCY = 100
_VERSION_HEADER = b"mcp-protocol-version"


class GuardedEndpoint:
    """The ASGI app: every request passes the guard, then reaches *manager*.
    A client ending its MCP session (``DELETE``) has its browsers closed."""

    def __init__(
        self, guard: auth.Guard, manager: StreamableHTTPSessionManager, clients: ClientPools
    ):
        self.guard = guard
        self.manager = manager
        self.clients = clients

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        refusal = self.guard.check(scope)
        if refusal is not None:
            await _reply(send, refusal.status, INVALID_REQUEST, refusal.message, refusal.headers)
            return
        version = dict(scope["headers"]).get(_VERSION_HEADER, b"").decode("latin-1")
        if version and version not in HANDSHAKE_PROTOCOL_VERSIONS:
            data = {"supported": list(HANDSHAKE_PROTOCOL_VERSIONS), "requested": version}
            message = "This server needs an MCP session: use the initialize handshake"
            await _reply(send, 400, UNSUPPORTED_PROTOCOL_VERSION, message, data=data)
            return
        if scope["method"] != "DELETE":
            await self.manager.handle_request(scope, receive, send)
            return
        status = await _status_of(self.manager.handle_request, scope, receive, send)
        # The id as the SDK read and validated it (the guard refuses a repeated one).
        client_id = Headers(scope=scope).get(MCP_SESSION_ID_HEADER)
        if status is not None and status < 400 and client_id:
            self.clients.forget(client_id)


def client_id(ctx: Any) -> str | None:
    """The MCP session of the HTTP request behind tool call *ctx*: the manager
    answers 404 to an unknown one, so it names a live client."""
    request = getattr(ctx, "request", None)
    return request.headers.get(MCP_SESSION_ID_HEADER) if request is not None else None


async def _status_of(app: Any, scope: Any, receive: Any, send: Any) -> int | None:
    status = None

    async def watch(message: dict[str, Any]) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        await send(message)

    await app(scope, receive, watch)
    return status


async def _reply(
    send: Any,
    status: int,
    code: int,
    message: str,
    headers: tuple[tuple[bytes, bytes], ...] = (),
    data: Any = None,
) -> None:
    """A JSON-RPC error (no id) at HTTP *status*: MCP clients show *message*."""
    body = JSONRPCError(
        jsonrpc="2.0", id=None, error=ErrorData(code=code, message=message, data=data)
    )
    payload = body.model_dump_json(by_alias=True, exclude_none=True).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                # Refused: close now, without reading a body the client may dribble.
                (b"connection", b"close"),
                *headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class _RequestDeadlines(H11Protocol):
    """uvicorn's h11 protocol with deadlines on each request: the head within
    HEADER_TIMEOUT, then the body within BODY_TIMEOUT. uvicorn's own keep-alive
    timer stops at the first byte, so a client dribbling headers or a body
    (slowloris) would otherwise hold a connection forever, token or not."""

    def connection_made(self, transport: Any) -> None:
        super().connection_made(transport)
        self._timer = self.loop.call_later(HEADER_TIMEOUT, self._overdue, h11.IDLE)
        self._body_timed = False

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
        super().connection_lost(exc)

    def _overdue(self, waiting: type) -> None:
        # Still waiting for the same part of the request: the client is too slow.
        if self.conn.their_state is waiting and not self.transport.is_closing():
            self.transport.close()


class _Uvicorn(uvicorn.Server):
    """uvicorn without its own signal handlers: the server's stop event rules."""

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def _bind(host: str, port: int) -> socket.socket:
    family, kind, proto, _, address = socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
    )[0]
    sock = socket.socket(family, kind, proto)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(address)
    except BaseException:
        sock.close()
        raise
    return sock


async def _prepare(config: ServerConfig, http: HttpConfig) -> tuple[str, socket.socket]:
    """The token and the bound socket, or a :class:`StartupError`."""
    try:
        token = await asyncio.to_thread(auth.load_or_create_token, config.token_path)
    except auth.TokenFileError as exc:
        raise StartupError(str(exc)) from None
    try:
        sock = await asyncio.to_thread(_bind, http.host, http.port)
    except OSError as exc:
        raise StartupError(
            f"cannot listen on {http.host}:{http.port}: {exc.strerror or exc}"
        ) from None
    return token, sock


def _announce(config: ServerConfig, http: HttpConfig, port: int) -> None:
    host = f"[{http.host}]" if ":" in http.host else http.host
    print(
        f"tellurium mcp: listening on http://{host}:{port}{auth.ENDPOINT} "
        f"(send 'Authorization: Bearer <token>', token in {config.token_path})",
        file=sys.stderr,
        flush=True,
    )


async def serve(config: ServerConfig, stop: asyncio.Event) -> bool:
    """Serve HTTP until *stop* is set; then close every client's sessions,
    saving the named ones (also when cancelled). True when *stop* ended it."""
    http = config.http or HttpConfig()
    token, sock = await _prepare(config, http)
    try:
        port = sock.getsockname()[1]
        guard = auth.Guard(token, auth.allowed_hosts(http.host), port)
        async with ClientPools(config, idle_timeout=http.idle_timeout) as clients:
            server = build_server(
                None, build_tools(config), use_pool=lambda ctx: clients.use(client_id(ctx))
            )
            manager = StreamableHTTPSessionManager(
                server,
                # Replies as plain JSON, not SSE: SDK clients refuse an SSE event
                # over 1 MiB, and a screenshot is up to 5 MB. The server sends no
                # notifications, so nothing needs the stream.
                json_response=True,
                session_idle_timeout=http.idle_timeout or None,
            )
            web = _Uvicorn(
                uvicorn.Config(
                    GuardedEndpoint(guard, manager, clients),
                    lifespan="off",
                    log_config=None,
                    log_level="warning",
                    access_log=False,
                    server_header=False,
                    timeout_graceful_shutdown=SHUTDOWN_GRACE,
                    http=_RequestDeadlines,
                    limit_concurrency=CONCURRENCY,
                )
            )
            return await _run(web, manager, sock, stop, lambda: _announce(config, http, port))
    finally:
        sock.close()


async def _run(
    web: _Uvicorn,
    manager: StreamableHTTPSessionManager,
    sock: socket.socket,
    stop: asyncio.Event,
    announce: Any,
) -> bool:
    serving: asyncio.Future[None] | None = None
    try:
        async with manager.run():
            serving = asyncio.ensure_future(web.serve(sockets=[sock]))
            stopping = asyncio.ensure_future(stop.wait())
            started = asyncio.ensure_future(_until_started(web))
            try:
                await asyncio.wait({serving, started}, return_when=asyncio.FIRST_COMPLETED)
                if web.started:
                    announce()
                await asyncio.wait({serving, stopping}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                stopping.cancel()
                started.cancel()
                web.should_exit = True  # no new connections; the sessions end below
    finally:
        if serving is not None:
            # The manager is closed: its sessions (and their event streams) are over.
            await asyncio.wait({serving}, timeout=SHUTDOWN_GRACE + 2)
            if not serving.done():
                serving.cancel()
    if serving.done() and not serving.cancelled() and serving.exception() is not None:
        raise serving.exception()  # type: ignore[misc]
    return stop.is_set()


async def _until_started(web: _Uvicorn) -> None:
    while not web.started:
        await asyncio.sleep(0.02)

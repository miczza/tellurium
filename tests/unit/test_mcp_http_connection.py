"""The MCP HTTP connection's lingering close, on a loopback socket and a bare
ASGI app (no MCP server, no Chrome)."""

from __future__ import annotations

import asyncio
import time

import pytest

pytest.importorskip("mcp")

import uvicorn  # noqa: E402
from uvicorn.server import ServerState  # noqa: E402

from tellurium.mcp import http_connection  # noqa: E402
from tellurium.mcp.http_connection import GuardedConnection  # noqa: E402


async def _refuse(scope, receive, send):
    """Answers without reading the body, as the guard does."""
    headers = [(b"content-length", b"2"), (b"connection", b"close")]
    await send({"type": "http.response.start", "status": 401, "headers": headers})
    await send({"type": "http.response.body", "body": b"{}"})


class _Reader:
    """Reads the body until the client is gone; notes when that was."""

    def __init__(self):
        self.gone_at: float | None = None

    async def __call__(self, scope, receive, send):
        while (await receive())["type"] != "http.disconnect":
            pass
        self.gone_at = time.monotonic()


async def _serve(app):
    loop = asyncio.get_running_loop()
    config = uvicorn.Config(app, lifespan="off", log_config=None)
    state = ServerState()
    server = await loop.create_server(
        lambda: GuardedConnection(config, state, {}, loop), "127.0.0.1", 0
    )
    return server, state, server.sockets[0].getsockname()[1]


def _head(length: int, port: int) -> bytes:
    return (
        f"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: {length}\r\n\r\n"
    ).encode()


async def _until_closed(state: ServerState, within: float) -> float:
    started = time.monotonic()
    while state.connections:
        assert time.monotonic() - started < within, "the server kept the connection"
        await asyncio.sleep(0.01)
    return time.monotonic() - started


@pytest.fixture
def drain(monkeypatch):
    def set_(seconds: float, size: int = http_connection.DRAIN_BYTES):
        monkeypatch.setattr(http_connection, "DRAIN_TIMEOUT", seconds)
        monkeypatch.setattr(http_connection, "DRAIN_BYTES", size)

    return set_


async def test_a_refusal_drains_a_body_still_coming_until_the_client_leaves(drain):
    drain(5)
    server, state, port = await _serve(_refuse)
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(_head(4096, port))
        reply = await asyncio.wait_for(reader.read(), 2)  # the end of stream: a half-close
        assert reply.startswith(b"HTTP/1.1 401") and reply.endswith(b"{}")
        writer.write(b" " * 4096)
        await writer.drain()
        await asyncio.sleep(0.1)
        assert len(state.connections) == 1  # still reading what comes
        writer.close()
        assert await _until_closed(state, within=1) < 1


async def test_the_drain_ends_at_its_deadline(drain):
    drain(0.3)
    server, state, port = await _serve(_refuse)
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(_head(10**9, port))
        await asyncio.wait_for(reader.read(), 2)
        try:
            assert 0.1 < await _until_closed(state, within=1.5)
        finally:
            writer.close()


async def test_the_drain_ends_past_its_byte_cap(drain):
    drain(5, size=1000)
    server, state, port = await _serve(_refuse)
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(_head(10**9, port))
        await asyncio.wait_for(reader.read(), 2)
        writer.write(b" " * 5000)
        try:
            assert await _until_closed(state, within=1) < 1
        finally:
            writer.close()


async def test_a_complete_request_is_closed_at_once(drain):
    drain(5)
    server, state, port = await _serve(_refuse)
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(_head(2, port) + b"{}")
        await asyncio.wait_for(reader.read(), 2)
        try:
            assert await _until_closed(state, within=0.5) < 0.5  # nothing left to drain
        finally:
            writer.close()


async def test_a_body_cut_at_its_deadline_frees_the_request_at_once(drain, monkeypatch):
    """The drain does not hold the request: the app sees the client gone at the
    deadline, while the connection still reads what the client sends."""
    drain(5)
    monkeypatch.setattr(http_connection, "BODY_TIMEOUT", 0.3)
    app = _Reader()
    server, state, port = await _serve(app)
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        started = time.monotonic()
        writer.write(_head(1000, port) + b"{")
        got = await asyncio.wait_for(reader.read(), 2)
        cut_after = time.monotonic() - started
        try:
            assert got == b"" and 0.2 < cut_after < 1
            await asyncio.sleep(0.05)
            assert app.gone_at is not None and app.gone_at - started < 1
            writer.write(b" ")  # drained, not reset
            await writer.drain()
            assert len(state.connections) == 1
        finally:
            writer.close()
        await _until_closed(state, within=1)

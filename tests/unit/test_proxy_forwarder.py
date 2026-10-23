"""ProxyForwarder against a fake local upstream proxy (audit M8)."""

from __future__ import annotations

import asyncio
import base64
import contextlib

import pytest

from tellurium.browser.proxy import ProxyForwarder

USER, PASSWORD = "user", "s3cret"
GOOD_AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
STEP = 3.0  # no single read may take longer: a hang fails fast


async def _read_head(reader: asyncio.StreamReader) -> tuple[bytes, dict[str, str]]:
    first = await reader.readline()
    headers: dict[str, str] = {}
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b""):
            return first, headers
        name, _, value = line.decode().partition(":")
        headers[name.strip().lower()] = value.strip()


async def _read_body(reader: asyncio.StreamReader, headers: dict[str, str]) -> bytes:
    if headers.get("transfer-encoding", "").lower() == "chunked":
        body = b""
        while True:
            size = int((await reader.readline()).split(b";")[0], 16)
            if size == 0:
                await reader.readline()
                return body
            body += await reader.readexactly(size)
            await reader.readline()
    return await reader.readexactly(int(headers.get("content-length", "0")))


class FakeUpstream:
    """An HTTP proxy that echoes each request and enforces Basic auth on CONNECT."""

    def __init__(self, credentials: str = GOOD_AUTH):
        self.credentials = credentials
        self.requests: list[tuple[bytes, dict[str, str], bytes]] = []
        self.connections = 0
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> FakeUpstream:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()

    @property
    def port(self) -> int:
        return self._server.sockets[0].getsockname()[1]

    async def _serve(self, reader, writer) -> None:
        self.connections += 1
        try:
            while True:
                first, headers = await _read_head(reader)
                if not first:
                    return
                if first.startswith(b"CONNECT"):
                    await self._connect(headers, reader, writer)
                    return
                body = await _read_body(reader, headers)
                self.requests.append((first, headers, body))
                reply = b"%s|%s|%s" % (
                    first.split()[0],
                    headers.get("proxy-authorization", "").encode(),
                    body,
                )
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(reply))
                writer.write(reply)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            return
        finally:
            writer.close()

    async def _connect(self, headers, reader, writer) -> None:
        if headers.get("proxy-authorization") != self.credentials:
            body = b"auth required"
            writer.write(
                b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                b'Proxy-Authenticate: Basic realm="fake"\r\n'
                b"Content-Length: %d\r\n\r\n%s" % (len(body), body)
            )
            await writer.drain()
            return
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        while data := await reader.read(65536):
            writer.write(data.upper())
            await writer.drain()


@contextlib.asynccontextmanager
async def _forwarder(upstream: FakeUpstream, password: str = PASSWORD):
    forwarder = ProxyForwarder("127.0.0.1", upstream.port, USER, password)
    await forwarder.start()
    try:
        yield forwarder
    finally:
        await asyncio.wait_for(forwarder.stop(), STEP)


async def _response(reader: asyncio.StreamReader) -> tuple[bytes, bytes]:
    first, headers = await asyncio.wait_for(_read_head(reader), STEP)
    body = await asyncio.wait_for(_read_body(reader, headers), STEP)
    return first, body


async def test_post_body_reaches_the_upstream():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(
            b"POST http://site.test/form HTTP/1.1\r\nHost: site.test\r\n"
            b"Content-Length: 11\r\n\r\nhello=world"
        )
        status, body = await _response(reader)
        writer.close()
    assert status.startswith(b"HTTP/1.1 200")
    assert body == b"POST|" + GOOD_AUTH.encode() + b"|hello=world"


async def test_chunked_body_reaches_the_upstream():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(
            b"POST http://site.test/up HTTP/1.1\r\nHost: site.test\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n"
        )
        _, body = await _response(reader)
        writer.close()
    assert body.endswith(b"|hello world")


async def test_keep_alive_requests_are_all_answered_with_auth():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        for i in range(3):
            writer.write(
                b"GET http://site.test/%d HTTP/1.1\r\nHost: site.test\r\n"
                b"Proxy-Connection: keep-alive\r\n\r\n" % i
            )
            status, body = await _response(reader)
            assert status.startswith(b"HTTP/1.1 200")
            assert body == b"GET|" + GOOD_AUTH.encode() + b"|"
        writer.close()
    assert len(up.requests) == 3
    assert all(h.get("proxy-authorization") == GOOD_AUTH for _, h, _ in up.requests)


async def test_client_credentials_are_replaced_not_duplicated():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(
            b"GET http://site.test/ HTTP/1.1\r\nHost: site.test\r\n"
            b"Proxy-Authorization: Basic Zm9vOmJhcg==\r\n\r\n"
        )
        await _response(reader)
        writer.close()
    first, headers, _ = up.requests[0]
    assert headers["proxy-authorization"] == GOOD_AUTH


async def test_connect_rejection_is_passed_through():
    async with FakeUpstream() as up, _forwarder(up, password="wrong") as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(b"CONNECT site.test:443 HTTP/1.1\r\nHost: site.test:443\r\n\r\n")
        status, body = await _response(reader)
        writer.close()
    assert status.startswith(b"HTTP/1.1 407"), status
    assert body == b"auth required"


async def test_connect_tunnel_relays_both_ways():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(b"CONNECT site.test:443 HTTP/1.1\r\nHost: site.test:443\r\n\r\n")
        status, _ = await asyncio.wait_for(_read_head(reader), STEP)
        assert status.startswith(b"HTTP/1.1 200")
        writer.write(b"ping")
        assert await asyncio.wait_for(reader.readexactly(4), STEP) == b"PING"
        writer.close()


async def test_unreachable_upstream_answers_502():
    forwarder = ProxyForwarder("127.0.0.1", 9, USER, PASSWORD)  # discard port: refused
    await forwarder.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", forwarder.port)
        writer.write(b"CONNECT site.test:443 HTTP/1.1\r\n\r\n")
        status, _ = await asyncio.wait_for(_read_head(reader), STEP)
        writer.close()
    finally:
        await forwarder.stop()
    assert status.startswith(b"HTTP/1.1 502")


async def test_stop_closes_open_connections():
    async with FakeUpstream() as up:
        forwarder = ProxyForwarder("127.0.0.1", up.port, USER, PASSWORD)
        await forwarder.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", forwarder.port)
        writer.write(b"CONNECT site.test:443 HTTP/1.1\r\n\r\n")
        await asyncio.wait_for(_read_head(reader), STEP)
        await asyncio.wait_for(forwarder.stop(), STEP)
        assert await asyncio.wait_for(reader.read(), STEP) == b""
        writer.close()


async def test_https_upstream_is_reached_over_tls(monkeypatch):
    seen: dict = {}

    async def fake_open(host, port, **kwargs):
        seen.update(kwargs, host=host, port=port)
        raise ConnectionRefusedError

    monkeypatch.setattr(asyncio, "open_connection", fake_open)
    forwarder = ProxyForwarder("proxy.test", 8443, USER, PASSWORD, tls=True)
    with pytest.raises(ConnectionRefusedError):
        await forwarder._open_upstream()
    assert seen["host"] == "proxy.test" and seen["ssl"] is not None
    assert seen.get("server_hostname") == "proxy.test"

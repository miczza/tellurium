"""ProxyForwarder against a fake local upstream proxy (audit M8)."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging

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


def _auth(forwarder: ProxyForwarder) -> bytes:
    """The header line that gets a client past the forwarder."""
    return b"Proxy-Authorization: %s\r\n" % forwarder.auth_header.encode()


async def _response(reader: asyncio.StreamReader) -> tuple[bytes, bytes]:
    first, headers = await asyncio.wait_for(_read_head(reader), STEP)
    body = await asyncio.wait_for(_read_body(reader, headers), STEP)
    return first, body


async def test_post_body_reaches_the_upstream():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(
            b"POST http://site.test/form HTTP/1.1\r\nHost: site.test\r\n"
            + _auth(fwd)
            + b"Content-Length: 11\r\n\r\nhello=world"
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
            + _auth(fwd)
            + b"Transfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n"
        )
        _, body = await _response(reader)
        writer.close()
    assert body.endswith(b"|hello world")


async def test_keep_alive_requests_are_all_answered_with_auth():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        for i in range(3):
            writer.write(
                b"GET http://site.test/%d HTTP/1.1\r\nHost: site.test\r\n" % i
                + _auth(fwd)
                + b"Proxy-Connection: keep-alive\r\n\r\n"
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
            b"GET http://site.test/ HTTP/1.1\r\nHost: site.test\r\n" + _auth(fwd) + b"\r\n"
        )
        await _response(reader)
        writer.close()
        secret = fwd.auth_header
    first, headers, _ = up.requests[0]
    assert headers["proxy-authorization"] == GOOD_AUTH
    assert secret not in repr(up.requests)  # the forwarder's secret stays local


async def test_connect_rejection_is_passed_through():
    async with FakeUpstream() as up, _forwarder(up, password="wrong") as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(
            b"CONNECT site.test:443 HTTP/1.1\r\nHost: site.test:443\r\n" + _auth(fwd) + b"\r\n"
        )
        status, body = await _response(reader)
        writer.close()
    assert status.startswith(b"HTTP/1.1 407"), status
    assert body == b"auth required"


async def test_connect_tunnel_relays_both_ways():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(
            b"CONNECT site.test:443 HTTP/1.1\r\nHost: site.test:443\r\n" + _auth(fwd) + b"\r\n"
        )
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
        writer.write(b"CONNECT site.test:443 HTTP/1.1\r\n" + _auth(forwarder) + b"\r\n")
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
        writer.write(b"CONNECT site.test:443 HTTP/1.1\r\n" + _auth(forwarder) + b"\r\n")
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


# --- review round: limits, timeouts, shutdown -------------------------------


async def test_stop_does_not_hang_on_a_connection_not_yet_handled():
    async with FakeUpstream() as up:
        forwarder = ProxyForwarder("127.0.0.1", up.port, USER, PASSWORD)
        await forwarder.start()
        server = forwarder._server
        _, writer = await asyncio.open_connection("127.0.0.1", forwarder.port)
        for _ in range(1000):  # accepted by the server, handler not started yet
            if getattr(server, "_clients", None):
                break
            await asyncio.sleep(0)
        await asyncio.wait_for(forwarder.stop(), STEP)
        writer.close()


async def test_oversized_request_head_is_refused():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(b"GET http://site.test/ HTTP/1.1\r\n" + _auth(fwd))
        for i in range(100):  # ~70 KiB in lines well under the per-line limit
            writer.write(b"X-Filler-%d: %s\r\n" % (i, b"a" * 700))
        writer.write(b"\r\n")
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), STEP) == b""
        writer.close()
    assert up.requests == []


async def test_a_huge_chunk_is_streamed_not_buffered():
    received = asyncio.Event()
    got: list[bytes] = []

    async def upstream(reader, writer):
        got.append(await reader.readuntil(b"\r\n\r\n"))
        data = b""
        while len(data) < 70_000:
            data += await reader.read(65536)
        received.set()
        writer.close()

    server = await asyncio.start_server(upstream, "127.0.0.1", 0)
    forwarder = ProxyForwarder("127.0.0.1", server.sockets[0].getsockname()[1], USER, PASSWORD)
    await forwarder.start()
    try:
        _, writer = await asyncio.open_connection("127.0.0.1", forwarder.port)
        writer.write(
            b"POST http://site.test/ HTTP/1.1\r\n"
            + _auth(forwarder)
            + b"Transfer-Encoding: chunked\r\n\r\n"
            b"6400000\r\n"  # a 100 MiB chunk, only its start is sent
        )
        writer.write(b"x" * 80_000)
        await writer.drain()
        await asyncio.wait_for(received.wait(), STEP)
        writer.close()
    finally:
        await forwarder.stop()
        server.close()


async def test_connect_without_an_upstream_answer_times_out():
    async def silent(reader, writer):
        await reader.read()  # accepts, never answers

    server = await asyncio.start_server(silent, "127.0.0.1", 0)
    forwarder = ProxyForwarder("127.0.0.1", server.sockets[0].getsockname()[1], USER, PASSWORD)
    forwarder.answer_timeout = 0.3
    await forwarder.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", forwarder.port)
        writer.write(b"CONNECT site.test:443 HTTP/1.1\r\n" + _auth(forwarder) + b"\r\n")
        status, _ = await asyncio.wait_for(_read_head(reader), STEP)
        writer.close()
    finally:
        await forwarder.stop()
        server.close()
    assert status.startswith(b"HTTP/1.1 504")


async def test_chunked_connect_rejection_body_is_passed_through():
    async def refusing(reader, writer):
        await _read_head(reader)
        writer.write(
            b"HTTP/1.1 407 Proxy Authentication Required\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n5\r\nauth \r\n8\r\nrequired\r\n0\r\n\r\n"
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(refusing, "127.0.0.1", 0)
    forwarder = ProxyForwarder("127.0.0.1", server.sockets[0].getsockname()[1], USER, PASSWORD)
    await forwarder.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", forwarder.port)
        writer.write(b"CONNECT site.test:443 HTTP/1.1\r\n" + _auth(forwarder) + b"\r\n")
        status, body = await _response(reader)
        writer.close()
    finally:
        await forwarder.stop()
        server.close()
    assert status.startswith(b"HTTP/1.1 407")
    assert body == b"auth required"


# --- the forwarder's own secret (S1) ----------------------------------------


def _secret(forwarder: ProxyForwarder) -> str:
    scheme, _, token = forwarder.auth_header.partition(" ")
    assert scheme == "Basic"
    user, _, secret = base64.b64decode(token).decode().partition(":")
    assert user == "tellurium"
    return secret


async def _refused(reader: asyncio.StreamReader) -> tuple[bytes, dict[str, str]]:
    """The forwarder's 407: its head, then the connection closes."""
    first, headers = await asyncio.wait_for(_read_head(reader), STEP)
    body = await asyncio.wait_for(_read_body(reader, headers), STEP)
    assert body == b""
    assert await asyncio.wait_for(reader.read(), STEP) == b""
    return first, headers


def _assert_challenge(first: bytes, headers: dict[str, str]) -> None:
    assert first.startswith(b"HTTP/1.1 407"), first
    assert headers["proxy-authenticate"] == 'Basic realm="tellurium"'
    assert headers["connection"].lower() == "close"


@pytest.mark.parametrize(
    "request_head",
    [
        b"GET http://site.test/ HTTP/1.1\r\nHost: site.test\r\n\r\n",
        b"CONNECT site.test:443 HTTP/1.1\r\nHost: site.test:443\r\n\r\n",
        b"POST http://site.test/ HTTP/1.1\r\nContent-Length: 5\r\n\r\nhello",
    ],
    ids=["get", "connect", "post"],
)
async def test_a_request_without_the_secret_gets_407_and_never_reaches_the_upstream(
    request_head,
):
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(request_head)
        _assert_challenge(*await _refused(reader))
        writer.close()
    assert up.connections == 0 and up.requests == []


@pytest.mark.parametrize(
    "credentials",
    [
        f"Basic {base64.b64encode(b'tellurium:wrong').decode()}",
        GOOD_AUTH,  # the upstream's credentials are not the forwarder's
        "Bearer abc",
        "Basic",
        "Basic !!!not-base64!!!",
    ],
)
async def test_a_wrong_secret_gets_407_and_never_reaches_the_upstream(credentials):
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(
            b"CONNECT site.test:443 HTTP/1.1\r\nProxy-Authorization: %s\r\n\r\n"
            % credentials.encode()
        )
        _assert_challenge(*await _refused(reader))
        writer.close()
    assert up.connections == 0


async def test_every_request_head_of_a_connection_needs_the_secret():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(
            b"GET http://site.test/1 HTTP/1.1\r\nHost: site.test\r\n" + _auth(fwd) + b"\r\n"
        )
        status, _ = await _response(reader)
        assert status.startswith(b"HTTP/1.1 200")
        writer.write(b"GET http://site.test/2 HTTP/1.1\r\nHost: site.test\r\n\r\n")
        _assert_challenge(*await _refused(reader))
        writer.close()
    assert [first.split()[1] for first, _, _ in up.requests] == [b"http://site.test/1"]


async def test_each_forwarder_has_its_own_long_random_secret():
    a = ProxyForwarder("127.0.0.1", 9, USER, PASSWORD)
    b = ProxyForwarder("127.0.0.1", 9, USER, PASSWORD)
    assert _secret(a) != _secret(b)
    assert len(_secret(a)) >= 43  # 32 random bytes, URL-safe base64


async def test_the_secret_never_shows_in_repr_or_logs(caplog):
    caplog.set_level(logging.DEBUG, logger="tellurium")
    async with FakeUpstream() as up, _forwarder(up, password="wrong") as fwd:
        secret = _secret(fwd)
        for head in (
            b"GET http://site.test/ HTTP/1.1\r\n\r\n",  # refused: no secret
            b"CONNECT site.test:443 HTTP/1.1\r\n" + _auth(fwd) + b"\r\n",  # upstream 407
            b"GET http://site.test/ HTTP/1.1\r\n" + _auth(fwd) + b"\r\n",
        ):
            reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
            writer.write(head)
            await asyncio.wait_for(_read_head(reader), STEP)
            writer.close()
        text = repr(fwd) + caplog.text
    unrelated = ProxyForwarder("127.0.0.1", 9, USER, PASSWORD)
    with pytest.raises(RuntimeError) as err:
        unrelated.port  # noqa: B018 - not started
    assert secret not in text
    assert _secret(unrelated) not in repr(unrelated) + str(err.value)


async def test_a_mute_connection_is_closed_after_the_head_timeout():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        fwd.head_timeout = 0.3
        connections = [await asyncio.open_connection("127.0.0.1", fwd.port) for _ in range(20)]
        for reader, writer in connections:
            assert await asyncio.wait_for(reader.read(), STEP) == b""
            writer.close()
        for _ in range(100):  # the handlers end with their connections
            if not fwd._clients:
                break
            await asyncio.sleep(0.01)
        assert not fwd._clients
    assert up.connections == 0


async def test_a_slow_head_is_cut_at_the_head_timeout():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        fwd.head_timeout = 0.3
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(b"GET http://site.test/ HTTP/1.1\r\n" + _auth(fwd))  # never ends
        assert await asyncio.wait_for(reader.read(), STEP) == b""
        writer.close()
    assert up.connections == 0


@pytest.mark.parametrize(
    "lines",
    [
        [b"Proxy-Authorization : {tok}"],  # space before the colon
        [b"Proxy-Authorization\t: {tok}"],
        [b"X-Filler: a", b" Proxy-Authorization: {tok}"],  # obs-fold
        [b"Proxy-Authorization: {tok}", b"X-Filler: a", b"\tProxy-Authorization: {tok}"],
        [b"Proxy-Authorization: {tok}", b" Proxy-Authorization : {tok}"],
        [b"Proxy-Authorization: {tok}", b"Proxy Authorization: {tok}"],
        [b"Proxy-Authorization: {tok}", b"no colon here"],
    ],
    ids=["space", "tab", "fold", "fold-tab", "both", "space-in-name", "no-colon"],
)
@pytest.mark.parametrize("method", [b"GET http://site.test/", b"CONNECT site.test:443"])
async def test_a_malformed_header_is_refused_and_the_secret_never_leaves(lines, method):
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        token = fwd.auth_header.encode()
        head = method + b" HTTP/1.1\r\n"
        head += b"".join(line.replace(b"{tok}", token) + b"\r\n" for line in lines)
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(head + b"\r\n")
        _assert_challenge(*await _refused(reader))
        writer.close()
    assert up.connections == 0 and up.requests == []


async def test_the_secret_header_is_removed_whatever_its_case():
    async with FakeUpstream() as up, _forwarder(up) as fwd:
        reader, writer = await asyncio.open_connection("127.0.0.1", fwd.port)
        writer.write(
            b"GET http://site.test/ HTTP/1.1\r\nPROXY-AUTHORIZATION: %s\r\n"
            b"proxy-authorization: %s\r\n\r\n" % ((fwd.auth_header.encode(),) * 2)
        )
        status, _ = await _response(reader)
        writer.close()
        secret = _secret(fwd)
    assert status.startswith(b"HTTP/1.1 200")
    assert secret not in repr(up.requests)

"""GeoIP lookups never leave the host directly: every request goes through the proxy.

Sockets are intercepted: any connection to a non-loopback address fails the
test. A local CONNECT proxy plays the far end of each tunnel itself.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import threading

import pytest

from tellurium.browser import engine as engine_mod
from tellurium.browser.launch_plan import LaunchPlan
from tellurium.browser.process import BrowserProcess
from tellurium.browser.proxy import forwarder_for
from tellurium.stealth import geoip

PAGES = {("ip.test", "/"): "203.0.113.5", ("country.test", "/203.0.113.5"): "IT"}


class TunnelProxy:
    """CONNECT proxy answering inside the tunnel from *pages*; 502 for other hosts."""

    def __init__(self, pages: dict[tuple[str, str], str]):
        self.pages = pages
        self.connects: list[str] = []
        self.heads: list[bytes] = []

    async def __aenter__(self) -> TunnelProxy:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, reader, writer) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            method, target, _ = head.split(b"\r\n", 1)[0].decode().split(" ", 2)
            self.connects.append(target)
            self.heads.append(head)
            host = target.rsplit(":", 1)[0]
            if method != "CONNECT" or not any(h == host for h, _ in self.pages):
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                return
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            request = await reader.readuntil(b"\r\n\r\n")
            path = request.split(b" ", 2)[1].decode()
            body = self.pages.get((host, path))
            status = b"200 OK" if body is not None else b"404 Not Found"
            data = (body or "").encode()
            writer.write(
                b"HTTP/1.1 "
                + status
                + b"\r\nContent-Length: %d\r\n" % len(data)
                + b"Connection: close\r\n\r\n"
                + data
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


def _spy(monkeypatch) -> list[tuple]:
    """Record every outgoing connection; refuse a non-loopback one.

    A ``socket.socketpair()`` is not one: on Windows Python builds it from a
    loopback connection, and asyncio makes one for each event loop (its
    self-pipe), so it would show up as a connection to an unknown port.
    """
    seen: list[tuple] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_socketpair = socket.socketpair
    pairing = threading.local()

    def socketpair(*args, **kwargs):
        pairing.on = True
        try:
            return real_socketpair(*args, **kwargs)
        finally:
            pairing.on = False

    def check(address) -> None:
        if getattr(pairing, "on", False):
            return
        seen.append(address)
        if isinstance(address, tuple) and not ipaddress.ip_address(address[0]).is_loopback:
            raise OSError(f"direct connection to {address} refused by the test")

    def connect(self, address):
        check(address)
        return real_connect(self, address)

    def connect_ex(self, address):
        check(address)
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "socketpair", socketpair)
    return seen


def test_a_socketpair_made_of_a_loopback_connection_is_not_counted(monkeypatch):
    def windows_socketpair():  # what Python does on Windows
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            client = socket.socket()
            client.connect(listener.getsockname())
            server, _ = listener.accept()
            return server, client

    monkeypatch.setattr(socket, "socketpair", windows_socketpair)
    seen = _spy(monkeypatch)
    for end in socket.socketpair():
        end.close()
    assert seen == []


@pytest.fixture
def connections(monkeypatch):
    """Every outgoing connection; a non-loopback one is refused and fails the test."""
    seen = _spy(monkeypatch)
    yield seen
    direct = [
        a for a in seen if isinstance(a, tuple) and not ipaddress.ip_address(a[0]).is_loopback
    ]
    assert not direct, f"direct connections: {direct}"


@pytest.fixture
def no_local_db(monkeypatch):
    def missing():
        raise FileNotFoundError("no GeoIP database in tests")

    monkeypatch.setattr(geoip, "_ensure_geolite2_db", missing)


@pytest.fixture
def test_services(monkeypatch, no_local_db):
    monkeypatch.setattr(geoip, "_EXIT_IP_SERVICES", ["http://ip.test/"])
    monkeypatch.setattr(geoip, "_ONLINE_COUNTRY_SERVICES", ["http://country.test/{ip}"])


async def test_plain_http_proxy_carries_both_lookups(connections, test_services):
    async with TunnelProxy(PAGES) as proxy:
        geo = await asyncio.to_thread(geoip.exit_geo, f"http://127.0.0.1:{proxy.port}")
    assert geo.country == "IT"
    assert proxy.connects == ["ip.test:80", "country.test:80"]
    assert {a[1] for a in connections} == {proxy.port}


async def test_the_forwarder_carries_both_lookups_with_the_credentials(connections, test_services):
    async with TunnelProxy(PAGES) as proxy:
        url = f"http://user:secret@127.0.0.1:{proxy.port}"
        forwarder = forwarder_for(url)
        await forwarder.start()
        forwarder_port = forwarder.port
        try:
            geo = await asyncio.to_thread(geoip.exit_geo, url, forwarder)
        finally:
            await forwarder.stop()
    assert geo.country == "IT"
    assert proxy.connects == ["ip.test:80", "country.test:80"]
    assert all(b"Proxy-Authorization: Basic dXNlcjpzZWNyZXQ=" in h for h in proxy.heads)
    # The forwarder's own secret got the lookups in, and stayed on this side.
    assert not [h for h in proxy.heads if forwarder.auth_header.encode() in h]
    assert {a[1] for a in connections} <= {proxy.port, forwarder_port}


async def test_real_services_are_only_asked_through_the_proxy(connections, no_local_db):
    async with TunnelProxy(PAGES) as proxy:
        with pytest.raises(RuntimeError, match="exit IP"):
            await asyncio.to_thread(geoip.exit_geo, f"http://127.0.0.1:{proxy.port}")
    assert proxy.connects == [
        "api.ipify.org:443",
        "checkip.amazonaws.com:443",
        "ifconfig.me:443",
        "icanhazip.com:443",
    ]
    assert {a[1] for a in connections} == {proxy.port}


async def test_country_service_only_through_the_proxy(connections, no_local_db, monkeypatch):
    monkeypatch.setattr(geoip, "_EXIT_IP_SERVICES", ["http://ip.test/"])
    async with TunnelProxy(PAGES) as proxy:
        with pytest.raises(FileNotFoundError):
            await asyncio.to_thread(geoip.exit_geo, f"http://127.0.0.1:{proxy.port}")
    assert proxy.connects == ["ip.test:80", "ipapi.co:443", "api.country.is:443"]


@pytest.mark.parametrize("proxy", ["socks5://127.0.0.1:1080", "https://127.0.0.1:3128"])
async def test_a_proxy_the_lookup_cannot_tunnel_through_makes_no_request(
    connections, test_services, proxy
):
    with pytest.raises(FileNotFoundError):
        await asyncio.to_thread(geoip.exit_geo, proxy)
    assert connections == []


def test_no_proxy_no_online_lookup(connections, no_local_db):
    with pytest.raises(FileNotFoundError):
        geoip.resolve_geoip("203.0.113.5")
    assert connections == []


@pytest.mark.parametrize("stealth", [False, True])
async def test_launch_plan_lookup_goes_through_the_forwarder(
    connections, test_services, monkeypatch, stealth
):
    async def fake_exec(self):
        return "/bin/true"

    monkeypatch.setattr(engine_mod.StockEngine, "get_executable", fake_exec)
    async with TunnelProxy(PAGES) as proxy:
        proc = BrowserProcess()
        plan = LaunchPlan(
            headless=True,
            proxy=f"http://user:secret@127.0.0.1:{proxy.port}",
            geoip=not stealth,
            stealth=stealth,
        )
        try:
            await plan.compose(proc)
        finally:
            await proc.close()
            if plan.stealth_engine is not None:
                plan.stealth_engine.close()
    assert "--accept-lang=it-IT,en" in plan.flags
    assert proxy.connects == ["ip.test:80", "country.test:80"]


class TricklingProxy:
    """A CONNECT proxy that accepts the tunnel, then answers one byte every
    *pace* seconds, for ever: each read gets data within its timeout."""

    def __init__(self, pace: float = 0.1):
        self.pace = pace
        self.open = 0
        self._handlers: set[asyncio.Task] = set()

    async def __aenter__(self) -> TricklingProxy:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()
        for task in self._handlers:
            task.cancel()
        await self._server.wait_closed()

    async def _handle(self, reader, writer) -> None:
        self._handlers.add(asyncio.current_task())
        self.open += 1
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await reader.readuntil(b"\r\n\r\n")
            head = b"HTTP/1.1 200 OK\r\nContent-Length: 1000000\r\n\r\n"
            for byte in head + b"1" * 1000000:
                writer.write(bytes([byte]))
                await writer.drain()
                await asyncio.sleep(self.pace)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self.open -= 1
            writer.close()


async def test_a_trickling_proxy_cannot_hold_a_lookup_past_its_timeout(
    connections, test_services, monkeypatch
):
    """Each read gets a byte within the socket timeout: the whole request is
    bounded all the same, and no thread or socket outlives the lookup."""
    import threading
    import time

    monkeypatch.setattr(geoip, "_REQUEST_TIMEOUT", 0.6)
    async with TricklingProxy() as proxy:
        errors: list[BaseException] = []

        def lookup() -> None:
            try:
                geoip.exit_geo(f"http://127.0.0.1:{proxy.port}", timeout=1.0)
            except BaseException as exc:  # noqa: BLE001 - checked below
                errors.append(exc)

        worker = threading.Thread(target=lookup, daemon=True)
        start = time.monotonic()
        worker.start()
        while worker.is_alive() and time.monotonic() - start < 3.0:
            await asyncio.sleep(0.05)
        assert not worker.is_alive(), "the lookup outlived its timeout"
        assert time.monotonic() - start < 2.0
        assert len(errors) == 1 and isinstance(errors[0], (TimeoutError, RuntimeError))
        for _ in range(100):  # the server sees each tunnel closed
            if proxy.open == 0:
                break
            await asyncio.sleep(0.05)
        assert proxy.open == 0

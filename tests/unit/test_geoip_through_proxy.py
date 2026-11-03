"""GeoIP lookups never leave the host directly: every request goes through the proxy.

Sockets are intercepted: any connection to a non-loopback address fails the
test. A local CONNECT proxy plays the far end of each tunnel itself.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket

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


@pytest.fixture
def connections(monkeypatch):
    """Every outgoing connection; a non-loopback one is refused and fails the test."""
    seen: list[tuple] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def check(address) -> None:
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

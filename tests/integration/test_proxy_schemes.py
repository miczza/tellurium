"""socks5:// and https:// proxies reach Chrome as such (audit M7, esito 3).

Each scenario puts a fake local upstream of the right protocol in front of
Chrome; the page only loads if Chrome speaks that protocol to it.
"""

from __future__ import annotations

import asyncio
import base64
import shutil
import ssl
import struct
import subprocess

import pytest

from tellurium import Browser
from tests.timeout_scale import scaled

pytestmark = pytest.mark.asyncio

PAGE = b"<!doctype html><title>%s</title><p>proxied</p>"
USER, PASSWORD = "user", "s3cret"
GOOD_AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()


async def _serve_one_http(reader, writer, title: bytes, seen: list) -> None:
    """Answer HTTP requests on a connection with a page titled *title*."""
    while request := await reader.readuntil(b"\r\n\r\n"):
        lines = request.decode().split("\r\n")
        headers = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
        seen.append((lines[0], headers.get("Proxy-Authorization", "")))
        body = PAGE % title
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\n\r\n%s"
            % (len(body), body)
        )
        await writer.drain()


class Socks5Proxy:
    """Minimal SOCKS5 (no auth, CONNECT only) that serves the page itself."""

    def __init__(self) -> None:
        self.targets: list[tuple[str, int]] = []
        self.requests: list = []

    async def __aenter__(self) -> Socks5Proxy:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()

    @property
    def port(self) -> int:
        return self._server.sockets[0].getsockname()[1]

    async def _serve(self, reader, writer) -> None:
        try:
            ver, n = await reader.readexactly(2)
            methods = await reader.readexactly(n)
            if ver != 5 or 0 not in methods:
                return
            writer.write(b"\x05\x00")
            _, cmd, _, atyp = await reader.readexactly(4)
            if atyp == 3:
                host = (await reader.readexactly((await reader.readexactly(1))[0])).decode()
            elif atyp == 1:
                host = ".".join(map(str, await reader.readexactly(4)))
            else:
                return
            (port,) = struct.unpack("!H", await reader.readexactly(2))
            self.targets.append((host, port))
            writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()
            await _serve_one_http(reader, writer, b"via socks5", self.requests)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


class HttpsProxy:
    """HTTP proxy reached over TLS that serves the page itself."""

    def __init__(self, context: ssl.SSLContext, auth: str | None = None) -> None:
        self._context = context
        self._auth = auth
        self.requests: list = []

    async def __aenter__(self) -> HttpsProxy:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0, ssl=self._context)
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()

    @property
    def port(self) -> int:
        return self._server.sockets[0].getsockname()[1]

    async def _serve(self, reader, writer) -> None:
        try:
            await _serve_one_http(reader, writer, b"via https proxy", self.requests)
        except (asyncio.IncompleteReadError, ConnectionError, ssl.SSLError):
            pass
        finally:
            writer.close()


@pytest.fixture(scope="module")
def certificate(tmp_path_factory):
    if shutil.which("openssl") is None:
        pytest.skip("openssl is needed to make the proxy's certificate")
    d = tmp_path_factory.mktemp("cert")
    cert, key = d / "cert.pem", d / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
         "-nodes", "-keyout", str(key), "-out", str(cert), "-days", "1",
         "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
        check=True, capture_output=True,
    )  # fmt: skip
    return cert, key


@pytest.fixture
def server_context(certificate):
    cert, key = certificate
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    return context


async def test_socks5_proxy_carries_the_page():
    async with Socks5Proxy() as proxy:
        browser = await Browser.launch(headless=True, proxy=f"socks5://127.0.0.1:{proxy.port}")
        try:
            tab = await browser.get("http://site.test/", timeout=scaled(15))
            assert await tab.eval("document.title") == "via socks5"
        finally:
            await browser.close()
    assert ("site.test", 80) in proxy.targets
    assert ("GET / HTTP/1.1", "") in proxy.requests  # origin-form: inside a tunnel


async def test_https_proxy_is_spoken_to_over_tls(server_context):
    async with HttpsProxy(server_context) as proxy:
        browser = await Browser.launch(
            headless=True,
            proxy=f"https://127.0.0.1:{proxy.port}",
            args=["--ignore-certificate-errors"],  # the test proxy's own certificate
        )
        try:
            tab = await browser.get("http://site.test/", timeout=scaled(15))
            assert await tab.eval("document.title") == "via https proxy"
        finally:
            await browser.close()
    assert ("GET http://site.test/ HTTP/1.1", "") in proxy.requests


async def test_authenticated_https_proxy_through_the_forwarder(
    server_context, certificate, monkeypatch
):
    from tellurium.browser import proxy as proxy_mod

    cert, _ = certificate
    trusting = ssl.create_default_context(cafile=cert)  # the forwarder trusts the test CA
    monkeypatch.setattr(proxy_mod.ssl, "create_default_context", lambda: trusting)
    async with HttpsProxy(server_context) as proxy:
        browser = await Browser.launch(
            headless=True, proxy=f"https://{USER}:{PASSWORD}@127.0.0.1:{proxy.port}"
        )
        try:
            tab = await browser.get("http://site.test/", timeout=scaled(15))
            assert await tab.eval("document.title") == "via https proxy"
        finally:
            await browser.close()
    assert ("GET http://site.test/ HTTP/1.1", GOOD_AUTH) in proxy.requests

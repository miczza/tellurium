"""Chrome through the credential forwarder to a fake local proxy (audit M7, M8; S1)."""

from __future__ import annotations

import asyncio
import base64
import shutil
import ssl
import subprocess
from urllib.parse import urlsplit

import pytest

from tellurium import Browser
from tellurium.browser.navigation import NavigationError
from tellurium.browser.proxy_auth import ProxyAuth

pytestmark = pytest.mark.asyncio

USER, PASSWORD = "user", "s3cret"
GOOD_AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
PAGE = b"<!doctype html><title>proxied</title><p>via the fake proxy</p>"

WORKER_JS = b"fetch('/from-worker').then(r => r.text()).then(t => postMessage(t));"
SW_JS = b"""
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('message', e => e.waitUntil(
  fetch('/from-sw').then(r => r.text()).then(t => e.source.postMessage(t))));
"""
#: Pages by full URL: (content type, body). Any other GET: PAGE at "/", else its path.
PAGES = {
    "http://site.test/worker.js": ("application/javascript", WORKER_JS),
    "http://site.test/sw.js": ("application/javascript", SW_JS),
    "http://site.test/popup.html": ("text/html", b"<!doctype html><title>popup</title>"),
    "http://site.test/opener.html": (
        "text/html",
        b'<!doctype html><a id="pop" href="/popup.html" target="_blank"'
        b' style="display:block;width:200px;height:50px">open</a>',
    ),
}


class FakeProxy:
    """An HTTP proxy that answers requests itself and wants *auth* (None: anything).

    A ``CONNECT`` with the right auth is closed at once, unless *tunnels*: then
    the proxy serves HTTP inside the tunnel itself, over TLS (*tls*) for port 443.
    """

    def __init__(
        self,
        auth: str | None = GOOD_AUTH,
        *,
        tunnels: bool = False,
        tls: ssl.SSLContext | None = None,
        pages: dict | None = None,
    ) -> None:
        self.auth = auth
        self.tunnels = tunnels
        self.tls = tls
        self.pages = {**PAGES, **(pages or {})}
        self.connections = 0
        self.requests: list[tuple[str, str]] = []  # (request line, auth)
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> FakeProxy:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()

    @property
    def port(self) -> int:
        return self._server.sockets[0].getsockname()[1]

    def lines(self) -> list[str]:
        return [line for line, _ in self.requests]

    async def _serve(self, reader, writer) -> None:
        self.connections += 1
        try:
            while first := await reader.readline():
                headers, body = await _read_message(reader)
                auth = headers.get("proxy-authorization", "")
                self.requests.append((first.decode().strip(), auth))
                if self.auth is not None and auth != self.auth:
                    writer.write(
                        b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n"
                    )
                    await writer.drain()
                    return
                method, target = first.split()[:2]
                if method == b"CONNECT":
                    if self.tunnels:
                        await self._tunnel(target.decode(), auth, reader, writer)
                    return
                await self._reply(writer, method, target.decode(), body)
        except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError):
            pass
        finally:
            writer.close()

    async def _tunnel(self, authority: str, auth: str, reader, writer) -> None:
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        host, _, port = authority.rpartition(":")
        scheme = "http"
        if port == "443" and self.tls is not None:
            await writer.start_tls(self.tls)
            scheme = "https"
        while first := await reader.readline():
            headers, body = await _read_message(reader)
            method, path = first.split()[:2]
            url = f"{scheme}://{host}{path.decode()}"
            self.requests.append((f"{method.decode()} {url} (tunnel)", auth))
            await self._reply(writer, method, url, body)

    async def _reply(self, writer, method: bytes, url: str, body: bytes) -> None:
        path = urlsplit(url).path
        status, extra = b"200 OK", b""
        if url in self.pages:
            kind, reply = self.pages[url]
            kind = kind.encode()
        elif path == "/401":
            status, kind, reply = b"401 Unauthorized", b"text/plain", b"denied"
            extra = b'WWW-Authenticate: Basic realm="site"\r\n'
        elif method != b"GET":
            kind, reply = b"text/plain", method + b"|" + body
        elif path == "/":
            kind, reply = b"text/html", PAGE
        else:
            kind, reply = b"text/plain", path.encode()
        writer.write(
            b"HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n%s"
            b"Connection: keep-alive\r\n\r\n%s" % (status, kind, len(reply), extra, reply)
        )
        await writer.drain()


async def _read_message(reader) -> tuple[dict[str, str], bytes]:
    headers = {}
    while (line := await reader.readline()) not in (b"\r\n", b""):
        name, _, value = line.decode().partition(":")
        headers[name.strip().lower()] = value.strip()
    body = await reader.readexactly(int(headers.get("content-length", "0")))
    return headers, body


def _url(proxy: FakeProxy, password: str = PASSWORD) -> str:
    return f"http://{USER}:{password}@127.0.0.1:{proxy.port}"


def _proxy_auth_tasks() -> list[asyncio.Task]:
    return [t for t in asyncio.all_tasks() if "ProxyAuth" in repr(t.get_coro())]


# --- as before S1 -------------------------------------------------------------


async def test_post_and_keep_alive_through_authenticated_proxy():
    async with FakeProxy() as proxy:
        browser = await Browser.launch(headless=True, proxy=_url(proxy))
        try:
            tab = await browser.get("http://site.test/", timeout=15)
            assert await tab.eval("document.title") == "proxied"
            for i in range(5):
                text = await tab.eval(
                    f"fetch('/echo', {{method: 'POST', body: 'hello-{i}'}}).then(r => r.text())",
                    timeout=10,
                )
                assert text == f"POST|hello-{i}"
        finally:
            await browser.close()
    assert all(auth == GOOD_AUTH for _, auth in proxy.requests)
    # Only the page's own requests: Chrome's background traffic (component updater,
    # POST to update.googleapis.com on Chrome 156) goes through the proxy too.
    posts = [line for line in proxy.lines() if line.startswith("POST http://site.test/")]
    assert len(posts) == 5
    # Keep-alive: requests share upstream connections instead of one each.
    assert proxy.connections < len(proxy.requests)
    assert not _proxy_auth_tasks()


async def test_upstream_407_reaches_chrome_as_an_auth_error():
    async with FakeProxy() as proxy:
        browser = await Browser.launch(headless=True, proxy=_url(proxy, "wrong"))
        try:
            with pytest.raises(NavigationError) as err:
                await browser.get("https://site.test/", timeout=15)
        finally:
            await browser.close()
    assert "SSL" not in str(err.value)
    assert "PROXY" in str(err.value) or "TUNNEL" in str(err.value), str(err.value)


# --- outcome 1: the forwarder is not an open proxy ----------------------------


@pytest.mark.parametrize(
    "head",
    [
        b"GET http://probe.test/ HTTP/1.1\r\nHost: probe.test\r\n\r\n",
        b"CONNECT probe.test:443 HTTP/1.1\r\nHost: probe.test:443\r\n\r\n",
        # The upstream's own credentials are not the forwarder's secret.
        b"CONNECT probe.test:443 HTTP/1.1\r\nProxy-Authorization: %s\r\n\r\n" % GOOD_AUTH.encode(),
    ],
    ids=["get", "connect", "upstream-credentials"],
)
async def test_a_local_process_without_the_secret_gets_407(head):
    async with FakeProxy() as proxy:
        browser = await Browser.launch(headless=True, proxy=_url(proxy))
        try:
            port = browser._proc.forwarder.port
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(head)
            status = await asyncio.wait_for(reader.readline(), 5)
            rest = await asyncio.wait_for(reader.read(), 5)  # then the connection closes
            writer.close()
            assert status.startswith(b"HTTP/1.1 407"), status
            assert b'Proxy-Authenticate: Basic realm="tellurium"' in rest
            # Chrome itself still gets through.
            tab = await browser.get("http://site.test/", timeout=15)
            assert await tab.eval("document.title") == "proxied"
        finally:
            await browser.close()
    assert not [line for line in proxy.lines() if "probe.test" in line]
    assert "http://site.test/" in " ".join(proxy.lines())


# --- outcome 2: Chrome browses as before --------------------------------------


@pytest.fixture(scope="module")
def tls_context(tmp_path_factory):
    if shutil.which("openssl") is None:
        pytest.skip("openssl is needed to make the test site's certificate")
    d = tmp_path_factory.mktemp("cert")
    cert, key = d / "cert.pem", d / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
         "-nodes", "-keyout", str(key), "-out", str(cert), "-days", "1",
         "-subj", "/CN=secure.test"],
        check=True, capture_output=True,
    )  # fmt: skip
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    return context


async def test_https_through_the_connect_tunnel(tls_context):
    async with FakeProxy(tunnels=True, tls=tls_context) as proxy:
        browser = await Browser.launch(
            headless=True,
            proxy=_url(proxy),
            args=["--ignore-certificate-errors"],  # the test site's own certificate
        )
        try:
            tab = await browser.get("https://secure.test/", timeout=15)
            assert await tab.eval("document.title") == "proxied"
        finally:
            await browser.close()
    assert ("CONNECT secure.test:443 HTTP/1.1", GOOD_AUTH) in proxy.requests
    assert "GET https://secure.test/ (tunnel)" in proxy.lines()


async def test_new_context_and_popup_go_through_the_proxy():
    async with FakeProxy() as proxy:
        browser = await Browser.launch(headless=True, proxy=_url(proxy))
        try:
            context = await browser.new_context()
            tab = await context.new_tab("http://site.test/")
            assert await tab.eval("document.title") == "proxied"

            await tab.get("http://site.test/opener.html", timeout=15)
            box = await (await tab.select("#pop")).bounding_box()
            await tab.mouse_click(box["x"] + 10, box["y"] + 10)
            popup = await browser.wait_for_tab("http://site.test/popup.html", timeout=15)
            for _ in range(100):
                if await popup.eval("document.readyState") == "complete":
                    break
                await asyncio.sleep(0.05)
            assert await popup.eval("document.title") == "popup"
        finally:
            await browser.close()
    assert "GET http://site.test/popup.html HTTP/1.1" in proxy.lines()
    assert all(auth == GOOD_AUTH for _, auth in proxy.requests)


async def test_a_worker_and_a_service_worker_go_through_the_proxy():
    async with FakeProxy() as proxy:
        browser = await Browser.launch(
            headless=True,
            proxy=_url(proxy),
            # A service worker needs a secure context; the fake site is plain HTTP.
            args=["--unsafely-treat-insecure-origin-as-secure=http://site.test"],
        )
        try:
            tab = await browser.get("http://site.test/", timeout=15)
            from_worker = await tab.eval(
                "new Promise(r => { new Worker('/worker.js').onmessage = e => r(e.data); })",
                timeout=15,
            )
            assert from_worker == "/from-worker"
            from_sw = await tab.eval(
                """(async () => {
                    const reg = await navigator.serviceWorker.register('/sw.js');
                    await navigator.serviceWorker.ready;
                    return await new Promise(r => {
                        navigator.serviceWorker.onmessage = e => r(e.data);
                        reg.active.postMessage('go');
                    });
                })()""",
                timeout=15,
            )
            assert from_sw == "/from-sw"
        finally:
            await browser.close()
    lines = proxy.lines()
    for path in ("/worker.js", "/from-worker", "/sw.js", "/from-sw"):
        assert f"GET http://site.test{path} HTTP/1.1" in lines, path


async def test_tab_intercept_still_sees_its_requests():
    async with FakeProxy() as proxy:
        browser = await Browser.launch(headless=True, proxy=_url(proxy))
        try:
            tab = await browser.get("http://site.test/", timeout=15)
            async with tab.intercept("*/api/*") as stream:
                pending = asyncio.ensure_future(
                    tab.eval("fetch('/api/x').then(r => r.text())", timeout=15)
                )
                request = await asyncio.wait_for(stream.__anext__(), 10)
                assert request.url == "http://site.test/api/x"
                await request.continue_()
                assert await pending == "/api/x"
        finally:
            await browser.close()
    assert "GET http://site.test/api/x HTTP/1.1" in proxy.lines()


@pytest.mark.parametrize("credentials", [True, False], ids=["fetch", "no-fetch"])
async def test_a_site_401_fails_as_it_does_without_fetch(credentials):
    """The ``Default`` answer: headless Chrome without Fetch fails a site's 401 the same way."""
    async with FakeProxy(auth=GOOD_AUTH if credentials else None) as proxy:
        url = _url(proxy) if credentials else f"http://127.0.0.1:{proxy.port}"
        browser = await Browser.launch(headless=True, proxy=url)
        try:
            with pytest.raises(NavigationError, match="ERR_INVALID_AUTH_CREDENTIALS"):
                await browser.get("http://site.test/401", timeout=15)
        finally:
            await browser.close()
    # No credentials were invented for the site: one request, no retry.
    assert proxy.lines().count("GET http://site.test/401 HTTP/1.1") == 1


async def test_stealth_geoip_goes_through_the_forwarder(monkeypatch):
    from tellurium.stealth import geoip

    def no_db():
        raise FileNotFoundError("no GeoIP database in tests")

    monkeypatch.setattr(geoip, "_ensure_geolite2_db", no_db)
    monkeypatch.setattr(geoip, "_EXIT_IP_SERVICES", ["http://ip.test/"])
    monkeypatch.setattr(geoip, "_ONLINE_COUNTRY_SERVICES", ["http://country.test/{ip}"])
    pages = {
        "http://ip.test/": ("text/plain", b"203.0.113.5"),
        "http://country.test/203.0.113.5": ("text/plain", b"JP"),
    }
    async with FakeProxy(tunnels=True, pages=pages) as proxy:
        browser = await Browser.launch(headless=True, proxy=_url(proxy), stealth=True)
        try:
            assert browser._stealth_profile.timezone == "Asia/Tokyo"
        finally:
            await browser.close()
    assert ("CONNECT ip.test:80 HTTP/1.1", GOOD_AUTH) in proxy.requests
    assert ("CONNECT country.test:80 HTTP/1.1", GOOD_AUTH) in proxy.requests


# --- outcome 4: without credentials nothing changes ---------------------------


async def test_without_credentials_no_forwarder_and_no_fetch():
    async with FakeProxy(auth=None) as proxy:
        browser = await Browser.launch(headless=True, proxy=f"http://127.0.0.1:{proxy.port}")
        try:
            assert browser._proc.forwarder is None and browser._proc.proxy_auth is None
            assert not browser._router.root._event_handlers.get("Fetch.requestPaused")
            tab = await browser.get("http://site.test/", timeout=15)
            assert await tab.eval("document.title") == "proxied"
        finally:
            await browser.close()
    assert ("GET http://site.test/ HTTP/1.1", "") in proxy.requests


# --- ownership ------------------------------------------------------------------


async def test_a_launch_cancelled_with_fetch_on_leaves_nothing_behind(monkeypatch):
    started = asyncio.Event()
    seen: dict = {}
    real_start = ProxyAuth.start

    async def start_then_hang(self):
        await real_start(self)
        seen["auth"] = self
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ProxyAuth, "start", start_then_hang)
    async with FakeProxy() as proxy:
        launching = asyncio.ensure_future(Browser.launch(headless=True, proxy=_url(proxy)))
        await asyncio.wait_for(started.wait(), 30)
        launching.cancel()
        with pytest.raises(asyncio.CancelledError):
            await launching
    auth = seen["auth"]
    assert not auth._active and not auth._tasks
    assert not _proxy_auth_tasks()
    port = auth._port
    with pytest.raises(OSError):
        _, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.close()

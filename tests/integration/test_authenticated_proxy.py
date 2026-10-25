"""Chrome through the credential forwarder to a fake local proxy (audit M7, M8)."""

from __future__ import annotations

import asyncio
import base64

import pytest

from tellurium import Browser
from tellurium.browser.navigation import NavigationError

pytestmark = pytest.mark.asyncio

USER, PASSWORD = "user", "s3cret"
GOOD_AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
PAGE = b"<!doctype html><title>proxied</title><p>via the fake proxy</p>"


class FakeProxy:
    """Answers every plain request itself; refuses CONNECT without the right auth."""

    def __init__(self) -> None:
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

    async def _serve(self, reader, writer) -> None:
        self.connections += 1
        try:
            while first := await reader.readline():
                headers = {}
                while (line := await reader.readline()) not in (b"\r\n", b""):
                    name, _, value = line.decode().partition(":")
                    headers[name.strip().lower()] = value.strip()
                auth = headers.get("proxy-authorization", "")
                self.requests.append((first.decode().strip(), auth))
                body = await reader.readexactly(int(headers.get("content-length", "0")))
                if auth != GOOD_AUTH:
                    writer.write(
                        b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n"
                    )
                    await writer.drain()
                    return
                if first.startswith(b"CONNECT"):
                    return
                method = first.split()[0]
                reply = PAGE if method == b"GET" else method + b"|" + body
                kind = b"text/html" if method == b"GET" else b"text/plain"
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
                    b"Connection: keep-alive\r\n\r\n%s" % (kind, len(reply), reply)
                )
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()


async def test_post_and_keep_alive_through_authenticated_proxy():
    async with FakeProxy() as proxy:
        browser = await Browser.launch(
            headless=True, proxy=f"http://{USER}:{PASSWORD}@127.0.0.1:{proxy.port}"
        )
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
    posts = [line for line, _ in proxy.requests if line.startswith("POST http://site.test/")]
    assert len(posts) == 5
    # Keep-alive: requests share upstream connections instead of one each.
    assert proxy.connections < len(proxy.requests)


async def test_upstream_407_reaches_chrome_as_an_auth_error():
    async with FakeProxy() as proxy:
        browser = await Browser.launch(
            headless=True, proxy=f"http://{USER}:wrong@127.0.0.1:{proxy.port}"
        )
        try:
            with pytest.raises(NavigationError) as err:
                await browser.get("https://site.test/", timeout=15)
        finally:
            await browser.close()
    assert "SSL" not in str(err.value)
    assert "PROXY" in str(err.value) or "TUNNEL" in str(err.value), str(err.value)

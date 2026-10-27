"""robots.txt through Chrome's own network stack (T8, part B).

A local HTTP proxy plays every site: it answers each request itself, from
routes the test writes, and records what reached it. Chrome is pointed at it
with ``proxy=``, so ``http://site.test/`` never leaves the machine.
"""

from __future__ import annotations

import asyncio
import base64

import pytest

from tellurium import Browser

pytestmark = pytest.mark.asyncio

ROBOTS = b"User-agent: *\nDisallow: /private\n"
PAGE = b"<!doctype html><title>%s</title><p>page</p>"


class SiteProxy:
    """An HTTP proxy that serves the sites itself.

    *routes* maps a path to ``(status, headers, body)``; any other path is a
    200 page titled with the path. Every request line and its headers are kept
    in *seen*.
    """

    def __init__(self, routes: dict[str, tuple[int, dict[str, str], bytes]] | None = None):
        self.routes = dict(routes or {})
        self.seen: list[tuple[str, dict[str, str]]] = []

    async def __aenter__(self) -> SiteProxy:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.sockets[0].getsockname()[1]}"

    def paths(self, path: str) -> list[str]:
        """The request lines of *path*, on any host."""
        return [line for line, _ in self.seen if line.split(" ")[1].endswith(path)]

    async def _serve(self, reader, writer) -> None:
        try:
            while request := await reader.readuntil(b"\r\n\r\n"):
                lines = request.decode().split("\r\n")
                headers = {
                    k.lower(): v for k, v in (ln.split(": ", 1) for ln in lines[1:] if ": " in ln)
                }
                self.seen.append((lines[0], headers))
                target = lines[0].split(" ")[1]
                path = "/" + target.split("://", 1)[-1].partition("/")[2]
                status, extra, body = self.routes.get(
                    path, (200, {"Content-Type": "text/html"}, PAGE % path.encode())
                )
                head = f"HTTP/1.1 {status} X\r\nContent-Length: {len(body)}\r\n"
                head += "".join(f"{k}: {v}\r\n" for k, v in extra.items())
                writer.write(head.encode() + b"\r\n" + body)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


async def _load(tab, url: str) -> dict:
    """``Network.loadNetworkResource`` from the tab's main frame, body read whole."""
    res = await tab._session.send(
        "Network.loadNetworkResource",
        {
            "frameId": tab._frame_id or tab._target_id,
            "url": url,
            "options": {"disableCache": False, "includeCredentials": False},
        },
        timeout=10,
    )
    resource = res["resource"]
    body = b""
    if stream := resource.get("stream"):
        while True:
            chunk = await tab._session.send("IO.read", {"handle": stream}, timeout=10)
            data = chunk.get("data", "")
            body += base64.b64decode(data) if chunk.get("base64Encoded") else data.encode()
            if chunk.get("eof"):
                break
        await tab._session.send("IO.close", {"handle": stream}, timeout=10)
    return {**resource, "body": body}


@pytest.mark.parametrize("stealth", [False, True], ids=["plain", "stealth"])
async def test_load_network_resource_goes_through_the_proxy_from_about_blank(stealth):
    """The mechanism the spec bets on: from a tab still on about:blank the load
    leaves through the proxy, follows a redirect, and sends no cookie."""
    routes = {
        "/robots.txt": (301, {"Location": "http://site.test/real-robots.txt"}, b""),
        "/real-robots.txt": (200, {"Content-Type": "text/plain"}, ROBOTS),
    }
    async with SiteProxy(routes) as proxy:
        browser = await Browser.launch(headless=True, stealth=stealth, proxy=proxy.url)
        try:
            tab = await browser.new_tab()
            res = await _load(tab, "http://site.test/robots.txt")
            assert res["success"], res
            assert res["httpStatusCode"] == 200
            assert res["body"] == ROBOTS
            assert proxy.paths("/robots.txt") == ["GET http://site.test/robots.txt HTTP/1.1"]
            assert proxy.paths("/real-robots.txt")
        finally:
            await browser.close()
    assert all("cookie" not in h for line, h in proxy.seen if "robots" in line)


async def _user_agents(stealth: bool) -> tuple[str | None, str | None]:
    """The User-Agent of a robots.txt load and of the page navigation after it."""
    routes = {"/robots.txt": (200, {"Content-Type": "text/plain"}, ROBOTS)}
    async with SiteProxy(routes) as proxy:
        browser = await Browser.launch(headless=True, stealth=stealth, proxy=proxy.url)
        try:
            tab = await browser.new_tab()
            await _load(tab, "http://site.test/robots.txt")
            await tab.get("http://site.test/page", timeout=15)
        finally:
            await browser.close()
    agent = {line.split(" ")[1]: h.get("user-agent") for line, h in proxy.seen}
    return agent.get("http://site.test/robots.txt"), agent.get("http://site.test/page")


async def test_load_network_resource_has_the_navigation_user_agent():
    robots, page = await _user_agents(stealth=False)
    assert robots and robots == page


@pytest.mark.xfail(
    strict=True,
    reason="Network.loadNetworkResource sends Chrome's own User-Agent, not the "
    "per-tab Emulation.setUserAgentOverride of stealth (docs/decisioni.md, T8-B)",
)
async def test_load_network_resource_has_the_stealth_user_agent():
    robots, page = await _user_agents(stealth=True)
    assert robots == page

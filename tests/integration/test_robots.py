"""robots.txt through Chrome's own network stack (T8, part B).

A local HTTP proxy plays every site: it answers each request itself, from
routes the test writes, and records what reached it. Chrome is pointed at it
with ``proxy=``, so ``http://site.test/`` never leaves the machine.
"""

from __future__ import annotations

import asyncio
import base64

import pytest

from tellurium import Browser, NavigationError, RobotsDisallowedError

pytestmark = pytest.mark.asyncio

ROBOTS = b"User-agent: *\nDisallow: /private\n"
PAGE = b"<!doctype html><title>%s</title><p>page</p>"


class SiteProxy:
    """An HTTP proxy that serves the sites itself (and, asked directly, one site).

    *routes* maps ``"host/path"`` or ``"/path"`` to ``(status, headers, body)``;
    any other path is a 200 page titled with the path. *delays* holds seconds to
    wait before answering a path. Every request line and its headers are kept
    in *seen*.
    """

    def __init__(self, routes: dict[str, tuple[int, dict[str, str], bytes]] | None = None):
        self.routes = dict(routes or {})
        self.delays: dict[str, float] = {}
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

    def hits(self, fragment: str) -> int:
        """How many requests had *fragment* in their target."""
        return sum(fragment in line.split(" ")[1] for line, _ in self.seen)

    async def _serve(self, reader, writer) -> None:
        try:
            while request := await reader.readuntil(b"\r\n\r\n"):
                lines = request.decode().split("\r\n")
                headers = {
                    k.lower(): v for k, v in (ln.split(": ", 1) for ln in lines[1:] if ": " in ln)
                }
                self.seen.append((lines[0], headers))
                target = lines[0].split(" ")[1]
                host, _, rest = target.split("://", 1)[-1].partition("/")
                path = "/" + rest
                host = host if "://" in target else headers.get("host", "")
                if delay := self.delays.get(path):
                    await asyncio.sleep(delay)
                default = (200, {"Content-Type": "text/html"}, PAGE % path.encode())
                status, extra, body = self.routes.get(host + path, self.routes.get(path, default))
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


HINTS = ("sec-ch-ua", "sec-ch-ua-platform", "sec-ch-ua-mobile")
_WORKER_UA = (
    "new Promise(r => { const w = new Worker(URL.createObjectURL(new Blob("
    "['postMessage(navigator.userAgent)']))); w.onmessage = e => r(e.data); })"
)


@pytest.mark.parametrize("headless", [True, False], ids=["headless", "headed"])
async def test_robots_txt_has_the_stealth_user_agent_of_the_page(headless):
    """With stealth, robots.txt (loaded by Robots from its hidden target) leaves
    with the User-Agent of the page loaded right after it, and no client hint
    contradicts the page's. Served straight from 127.0.0.1, a secure context,
    so the page does send its client hints."""
    async with SiteProxy({"/robots.txt": (200, TEXT, ROBOTS)}) as site:
        browser = await Browser.launch(headless=headless, stealth=True)
        try:
            tab = await browser.new_tab()
            assert await tab.is_allowed(site.url + "/public")
            await tab.get(site.url + "/page", timeout=15)
            main = await tab.eval("navigator.userAgent")
            brands = await tab.eval("navigator.userAgentData.brands.map(b => b.brand)")
            worker = await tab.eval(_WORKER_UA)
        finally:
            await browser.close()
    seen = {line.split(" ")[1]: h for line, h in site.seen}
    robots, page = seen["/robots.txt"], seen["/page"]
    assert "HeadlessChrome" not in robots["user-agent"]
    assert robots["user-agent"] == page["user-agent"] == main == worker
    assert page["sec-ch-ua"] and "Google Chrome" in brands
    for hint in HINTS:  # loadNetworkResource sends none (docs/decisioni.md)
        assert robots.get(hint) in (None, page[hint]), hint


TEXT = {"Content-Type": "text/plain"}


@pytest.fixture
async def site():
    """A proxy playing ``site.test`` (robots.txt: ``/private`` disallowed) and a
    plain browser behind it, respecting robots.txt."""
    async with SiteProxy({"/robots.txt": (200, TEXT, ROBOTS)}) as proxy:
        browser = await Browser.launch(headless=True, proxy=proxy.url, respect_robots=True)
        try:
            yield proxy, browser
        finally:
            await browser.close()


async def test_a_disallowed_path_is_not_requested(site):
    proxy, browser = site
    tab = await browser.new_tab()
    with pytest.raises(RobotsDisallowedError) as caught:
        await tab.get("http://site.test/private/page?x=1", timeout=15)
    assert str(caught.value) == "robots.txt of http://site.test disallows /private/page?x=1"
    assert isinstance(caught.value, NavigationError)
    await tab.get("http://site.test/public", timeout=15)
    assert await tab.eval("document.title") == "/public"
    assert proxy.hits("/private") == 0
    assert proxy.hits("/robots.txt") == 1
    assert tab.url == "http://site.test/public"


async def test_new_tab_and_browser_get_are_checked_too(site):
    proxy, browser = site
    before = len(browser.tabs)
    with pytest.raises(RobotsDisallowedError):
        await browser.new_tab("http://site.test/private")
    assert len(browser.tabs) == before  # the blank tab it made is closed again
    with pytest.raises(RobotsDisallowedError):
        await browser.get("http://site.test/private")
    context = await browser.new_context()
    try:
        with pytest.raises(RobotsDisallowedError):
            await context.new_tab("http://site.test/private")
        assert context.tabs == []
        tab = await context.new_tab("http://site.test/open")
        assert await tab.eval("document.title") == "/open"
    finally:
        await context.close()
    assert proxy.hits("/private") == 0


async def test_clicks_and_redirects_are_not_blocked(site):
    """Only the navigations tellurium starts are checked (spec, decision 3)."""
    proxy, browser = site
    proxy.routes["/hop"] = (302, {"Location": "/private/landing"}, b"")
    tab = await browser.new_tab()
    await tab.get("http://site.test/hop", timeout=15)
    assert await tab.eval("document.title") == "/private/landing"
    assert not await tab.is_allowed("http://site.test/private/landing")


async def test_a_hundred_concurrent_gets_download_robots_txt_once(site):
    proxy, browser = site
    proxy.delays["/robots.txt"] = 0.5
    tabs = [await browser.new_tab() for _ in range(10)]
    gets = [tabs[i % 10].get(f"http://site.test/private/{i}", timeout=20) for i in range(100)]
    results = await asyncio.gather(*gets, return_exceptions=True)
    assert all(isinstance(r, RobotsDisallowedError) for r in results), results
    assert proxy.paths("/robots.txt") == ["GET http://site.test/robots.txt HTTP/1.1"]
    assert proxy.hits("/private") == 0


@pytest.mark.parametrize("status, allowed", [(404, True), (410, True), (500, False), (503, False)])
async def test_status_of_robots_txt(site, status, allowed):
    proxy, browser = site
    proxy.routes["other.test/robots.txt"] = (status, TEXT, b"User-agent: *\nDisallow: /\n")
    tab = await browser.new_tab()
    assert await tab.is_allowed("http://other.test/page") is allowed
    if allowed:
        await tab.get("http://other.test/page", timeout=15)
    else:
        with pytest.raises(RobotsDisallowedError):
            await tab.get("http://other.test/page", timeout=15)
    assert proxy.hits("other.test/page") == int(allowed)
    assert proxy.hits("other.test/robots.txt") == 1


async def test_an_unreachable_robots_txt_disallows_everything():
    """A network error (here: no proxy listening) counts as unreachable."""
    browser = await Browser.launch(headless=True, proxy="http://127.0.0.1:9", respect_robots=True)
    try:
        tab = await browser.new_tab()
        assert not await tab.is_allowed("http://site.test/x")
        with pytest.raises(RobotsDisallowedError):
            await tab.get("http://site.test/x", timeout=15)
    finally:
        await browser.close()


async def test_a_hidden_target_that_cannot_open_fails_the_get(site, monkeypatch):
    """Creating the hidden target (here: given no time) is part of the
    navigation: its failure is a NavigationError with the cause chained."""
    from tellurium.browser import robots

    proxy, browser = site
    tab = await browser.new_tab()
    monkeypatch.setattr(robots, "_OPEN_TIMEOUT", 1e-6)
    with pytest.raises(NavigationError, match="robots.txt of http://site.test") as caught:
        await tab.get("http://site.test/page", timeout=15)
    assert isinstance(caught.value.__cause__, TimeoutError)
    assert not isinstance(caught.value, RobotsDisallowedError)
    assert proxy.hits("/page") == 0
    monkeypatch.undo()
    await tab.get("http://site.test/page", timeout=15)  # not cached: opened again
    assert proxy.hits("/page") == 1


async def test_a_robots_txt_that_never_answers_times_out(site, monkeypatch):
    from tellurium.browser import robots

    monkeypatch.setattr(robots, "FETCH_TIMEOUT", 1.0)
    proxy, browser = site
    proxy.delays["/robots.txt"] = 5
    proxy.routes["slow.test/robots.txt"] = (200, TEXT, b"")
    tab = await browser.new_tab()
    loop = asyncio.get_running_loop()
    start = loop.time()
    assert not await tab.is_allowed("http://slow.test/page")
    assert loop.time() - start < 4


async def test_a_navigation_timeout_bounds_the_robots_wait(site, monkeypatch):
    proxy, browser = site
    proxy.delays["/robots.txt"] = 5
    tab = await browser.new_tab()
    loop = asyncio.get_running_loop()
    start = loop.time()
    with pytest.raises(TimeoutError) as caught:
        await tab.get("http://late.test/page", timeout=1)
    assert loop.time() - start < 3
    assert caught.value.phase == "robots.txt"
    assert proxy.hits("late.test/page") == 0


async def test_is_allowed_takes_a_timeout(site):
    """The caller bounds the wait; the download goes on and fills the cache."""
    proxy, browser = site
    proxy.delays["/robots.txt"] = 1.5
    proxy.routes["wait.test/robots.txt"] = (200, TEXT, b"User-agent: *\nDisallow: /no\n")
    tab = await browser.new_tab()
    loop = asyncio.get_running_loop()
    start = loop.time()
    with pytest.raises(TimeoutError) as caught:
        await tab.is_allowed("http://wait.test/yes", timeout=0.3)
    assert loop.time() - start < 1
    assert caught.value.phase == "robots.txt"
    assert not await tab.is_allowed("http://wait.test/no", timeout=10)
    assert proxy.hits("wait.test/robots.txt") == 1


async def test_redirects_of_robots_txt_are_followed(site):
    proxy, browser = site
    proxy.routes["moved.test/robots.txt"] = (301, {"Location": "http://moved.test/r2"}, b"")
    proxy.routes["moved.test/r2"] = (302, {"Location": "http://moved.test/r3"}, b"")
    proxy.routes["moved.test/r3"] = (200, TEXT, b"User-agent: *\nDisallow: /no\n")
    tab = await browser.new_tab()
    assert not await tab.is_allowed("http://moved.test/no")
    assert await tab.is_allowed("http://moved.test/yes")


async def test_robots_agent_picks_its_group():
    robots_txt = b"User-agent: *\nDisallow: /\n\nUser-agent: mybot\nDisallow: /secret\n"
    async with SiteProxy({"/robots.txt": (200, TEXT, robots_txt)}) as proxy:
        browser = await Browser.launch(
            headless=True, proxy=proxy.url, respect_robots=True, robots_agent="mybot"
        )
        try:
            tab = await browser.get("http://site.test/page", timeout=15)
            assert await tab.eval("document.title") == "/page"
            with pytest.raises(RobotsDisallowedError):
                await tab.get("http://site.test/secret", timeout=15)
        finally:
            await browser.close()


async def test_without_the_flag_no_robots_txt_is_requested():
    async with SiteProxy({"/robots.txt": (200, TEXT, ROBOTS)}) as proxy:
        browser = await Browser.launch(headless=True, proxy=proxy.url)
        try:
            tab = await browser.get("http://site.test/private", timeout=15)
            await browser.new_tab("http://site.test/private/2")
            await tab.get("http://site.test/x", timeout=15)
            assert proxy.hits("/robots.txt") == 0
            # is_allowed answers without the flag: it downloads the file, once
            assert not await tab.is_allowed("http://site.test/private")
            assert await tab.is_allowed("http://site.test/x")
            assert proxy.hits("/robots.txt") == 1
        finally:
            await browser.close()


async def test_non_web_urls_are_never_checked(site):
    proxy, browser = site
    tab = await browser.new_tab()
    await tab.get("about:blank", timeout=15)
    await tab.get("data:text/html,<title>d</title>", timeout=15)
    assert await tab.is_allowed("about:blank")
    assert proxy.hits("robots.txt") == 0


async def test_closing_the_browser_mid_download(site):
    proxy, browser = site
    proxy.delays["/robots.txt"] = 5
    tab = await browser.new_tab()
    waiting = asyncio.ensure_future(tab.get("http://site.test/private", timeout=30))
    await asyncio.sleep(0.5)
    await asyncio.wait_for(browser.close(), 10)
    with pytest.raises(ConnectionError):
        await waiting


async def test_a_page_with_a_strict_csp_does_not_block_the_download(site):
    """From the page itself the load would obey its connect-src (CSP violation)."""
    proxy, browser = site
    strict = {"Content-Type": "text/html", "Content-Security-Policy": "default-src 'none'"}
    proxy.routes["csp.test/page"] = (200, strict, b"<title>csp</title>")
    proxy.routes["csp.test/robots.txt"] = (200, TEXT, b"")
    tab = await browser.new_tab("http://csp.test/page")
    await tab.get("http://site.test/public", timeout=15)
    with pytest.raises(RobotsDisallowedError):
        await tab.get("http://site.test/private", timeout=15)


async def test_the_first_tab_on_the_new_tab_page_is_checked(site):
    """Chrome's first tab shows chrome://newtab, whose CSP refuses any load."""
    proxy, browser = site
    tab = await browser.get("http://site.test/public", timeout=15)
    assert await tab.eval("document.title") == "/public"
    with pytest.raises(RobotsDisallowedError):
        await browser.get("http://site.test/private", timeout=15)


async def test_the_hidden_target_is_not_a_tab(site):
    proxy, browser = site
    before = [t._target_id for t in browser.tabs]
    tab = await browser.new_tab()
    assert await tab.is_allowed("http://site.test/public")
    await asyncio.sleep(0.3)
    assert [t._target_id for t in browser.tabs] == [*before, tab._target_id]


async def test_mcp_respect_robots_refuses_navigate_and_tab_open(tmp_path):
    """E5: ``tellurium mcp --respect-robots`` answers with the reason instead."""
    pytest.importorskip("mcp")
    from tests.integration.test_mcp_stdio import _call, _error, _server, _text

    async with SiteProxy({"/robots.txt": (200, TEXT, ROBOTS)}) as site:
        async with _server(tmp_path, "--respect-robots") as client:
            opened = (await _call(client, "session-open")).structured_content
            sid, tid = opened["sessionId"], opened["targetId"]
            message = await _error(client, "navigate", targetId=tid, url=f"{site.url}/private/x")
            assert f"robots.txt of {site.url} disallows /private/x" in message
            message = await _error(client, "tab-open", sessionId=sid, url=f"{site.url}/private")
            assert f"robots.txt of {site.url} disallows /private" in message
            await _call(client, "navigate", targetId=tid, url=f"{site.url}/public")
            assert "page" in await _text(client, tid)
            listed = (await _call(client, "tab-list", sessionId=sid)).structured_content
        assert site.hits("/private") == 0
        assert site.hits("/robots.txt") == 1
        assert len(listed["tabs"]) == 1  # neither the refused tab nor the hidden target

        async with _server(tmp_path) as client:  # without the flag: opened
            tid = (await _call(client, "session-open")).structured_content["targetId"]
            await _call(client, "navigate", targetId=tid, url=f"{site.url}/private/x")
        assert site.hits("/private") == 1
        assert site.hits("/robots.txt") == 1


async def test_the_hidden_target_stays_out_of_the_window_when_headed():
    async with SiteProxy({"/robots.txt": (200, TEXT, ROBOTS)}) as proxy:
        browser = await Browser.launch(headless=False, proxy=proxy.url, respect_robots=True)
        try:
            tab = await browser.get("http://site.test/public", timeout=15)
            assert not await tab.is_allowed("http://site.test/private")
            infos = (await browser._router.root.send("Target.getTargets", {}))["targetInfos"]
            pages = [i["targetId"] for i in infos if i["type"] == "page"]
            assert pages == [t._target_id for t in browser.tabs]
            assert any(i["type"] == "other" and i["url"] == "about:blank" for i in infos)
        finally:
            await browser.close()

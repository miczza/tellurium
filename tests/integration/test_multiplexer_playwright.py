"""Playwright, the real one, against the multiplexer: ``connect_over_cdp`` with the
Bearer header, a page on a local fixture, and one Chrome of its own per client.
Only the Python package is needed (its Node driver), not Playwright's browsers."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("websockets")
async_api = pytest.importorskip("playwright.async_api")

from tellurium.browser.launcher import find_chrome  # noqa: E402
from tests.integration.test_authenticated_proxy import (  # noqa: E402
    GOOD_AUTH,
    PASSWORD,
    USER,
    FakeProxy,
)
from tests.integration.test_multiplexer import serving, token_file  # noqa: E402, F401
from tests.integration.test_raw_chrome import (  # noqa: E402, F401 - autouse fixture
    _alive,
    _profiles,
    _wait_until,
    private_tempdir,
)
from tests.platform_marks import needs_proc  # noqa: E402

#: Milliseconds Playwright may take for the connection (the place launches Chrome).
CONNECT_TIMEOUT = 90_000


def _busy(mux) -> list[dict]:
    return [s for s in mux.status()["slots"] if s["state"] == "busy"]


@needs_proc
async def test_connect_over_cdp_opens_a_page_and_gives_the_chrome_back(
    local_server,
    private_tempdir,  # noqa: F811
):
    async with serving(2) as mux, async_api.async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(
            mux.url, headers={"Authorization": f"Bearer {mux.token}"}, timeout=CONNECT_TIMEOUT
        )
        try:
            (slot,) = _busy(mux)
            page = await browser.new_page()
            await page.goto(f"{local_server}/basic.html", timeout=30_000)
            assert await page.title() == "Basic Test Page"
            assert await page.evaluate("1 + 1") == 2
            await page.close()
        finally:
            await browser.close()
        assert await _wait_until(lambda: not _alive(slot["pid"]), 30)
        assert await _wait_until(lambda: not _busy(mux), 30)
        assert mux.status()["connections"] == 1 and mux.status()["crashes"] == 0
    assert _profiles(private_tempdir) == []


@needs_proc
async def test_two_playwright_clients_get_two_chromes(
    local_server,
    private_tempdir,  # noqa: F811
):
    """Patched engine flags on the stock binary, so each Chrome shows its seed."""
    stock = await find_chrome()
    async with serving(2, browser="patched", executable=stock) as mux:
        headers = {"Authorization": f"Bearer {mux.token}"}
        async with async_api.async_playwright() as first, async_api.async_playwright() as second:
            browsers = await asyncio.gather(
                first.chromium.connect_over_cdp(mux.url, headers=headers, timeout=CONNECT_TIMEOUT),
                second.chromium.connect_over_cdp(mux.url, headers=headers, timeout=CONNECT_TIMEOUT),
            )
            try:
                pages = [await b.new_page() for b in browsers]
                await asyncio.gather(
                    *(p.goto(f"{local_server}/basic.html", timeout=30_000) for p in pages)
                )
                assert [await p.title() for p in pages] == ["Basic Test Page"] * 2
                busy = _busy(mux)
                assert len(busy) == 2
                assert len({s["pid"] for s in busy}) == 2
                assert len({s["seed"] for s in busy}) == 2
            finally:
                await asyncio.gather(*(b.close() for b in browsers))
        assert await _wait_until(lambda: not any(_alive(s["pid"]) for s in busy), 30)
        # Each client's temporary profile went with its Chrome.
        assert await _wait_until(lambda: len(_profiles(private_tempdir)) == 0, 30)


async def test_connect_over_cdp_without_the_token_is_refused():
    async with serving() as mux, async_api.async_playwright() as playwright:
        with pytest.raises(async_api.Error) as refused:
            await playwright.chromium.connect_over_cdp(mux.url, timeout=CONNECT_TIMEOUT)
        assert "401" in str(refused.value)
        assert mux.token not in str(refused.value)
        assert mux.status()["connections"] == 0
        assert all(s["launches"] == 0 for s in mux.status()["slots"])


@needs_proc
async def test_playwright_behind_an_authenticated_proxy_with_route_and_a_new_context(
    private_tempdir,  # noqa: F811
):
    """Outcome 3 of S1: the relay answers the forwarder's challenge, even with
    Playwright's own ``Fetch`` on (``route``, set before the first request of a
    context, so the challenge comes while it is on), and Playwright sees none of it."""
    async with FakeProxy() as proxy:
        url = f"http://{USER}:{PASSWORD}@127.0.0.1:{proxy.port}"
        async with serving(1, proxies=[url]) as mux, async_api.async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(
                mux.url, headers={"Authorization": f"Bearer {mux.token}"}, timeout=CONNECT_TIMEOUT
            )
            try:
                (slot,) = _busy(mux)
                answered = mux._pool.places[0].chrome._proc.proxy_auth._answered
                routed: list[str] = []

                async def go_on(route) -> None:
                    routed.append(route.request.url)
                    await route.continue_()

                page = await browser.new_page()
                await page.route("**", go_on)
                await page.goto("http://site.test/", timeout=30_000)
                assert await page.title() == "proxied"
                await page.goto("http://site.test/routed", timeout=30_000)
                assert await page.inner_text("body") == "/routed"
                assert routed == ["http://site.test/", "http://site.test/routed"]
                challenged = len(answered)
                assert challenged >= 1  # the forwarder's 407 came with the route on

                context = await browser.new_context()  # its own proxy auth cache
                await context.route("**", go_on)
                other = await context.new_page()
                await other.goto("http://site.test/", timeout=30_000)
                assert await other.title() == "proxied"
                assert len(answered) > challenged
                assert routed[-1] == "http://site.test/"
                plain = await browser.new_context()  # and one without route
                await (await plain.new_page()).goto("http://site.test/plain", timeout=30_000)
                await plain.close()
                await context.close()
            finally:
                await browser.close()
            assert await _wait_until(lambda: not _alive(slot["pid"]), 30)
        wanted = {f"GET http://site.test/{p} HTTP/1.1" for p in ("", "routed", "plain")}
        assert wanted <= set(proxy.lines())
        assert {auth for _, auth in proxy.requests} == {GOOD_AUTH}
        assert _profiles(private_tempdir) == []

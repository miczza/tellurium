"""Cookie jar operations against a real Chrome (audit M6, m10)."""

import asyncio

import pytest

from tellurium.browser.cookie import Cookie
from tests.timeout_scale import scaled

pytestmark = pytest.mark.asyncio

_JAR = [
    Cookie(name="a", value="1", domain=".example.com"),
    Cookie(name="b", value="2", domain="sub.example.com", path="/x"),
    Cookie(name="c", value="3", domain=".notexample.com"),
    Cookie(name="d", value="4", domain="other.org", http_only=True, secure=True),
]


def _names(cookies):
    return sorted(c.name for c in cookies)


async def test_get_cookies_matches_domain_not_substring(browser):
    await browser.set_cookies(_JAR)
    assert _names(await browser.get_cookies("example.com")) == ["a", "b"]
    assert _names(await browser.get_cookies("notexample.com")) == ["c"]
    assert _names(await browser.get_cookies()) == ["a", "b", "c", "d"]


async def test_clear_cookies_removes_everything(browser):
    await browser.set_cookies(_JAR)
    await browser.clear_cookies()
    assert await browser.get_cookies() == []


async def test_clear_cookies_for_domain_keeps_the_others(browser):
    await browser.set_cookies(_JAR)
    await browser.clear_cookies("example.com")
    assert _names(await browser.get_cookies()) == ["c", "d"]
    survivor = next(c for c in await browser.get_cookies() if c.name == "d")
    assert survivor.http_only and survivor.secure


async def test_cookies_are_cleared_in_a_page(browser, local_server):
    tab = await browser.get(local_server + "/basic.html")
    await tab.eval("document.cookie = 'seen=1; path=/'")
    # A cookie written by the renderer reaches the browser's store asynchronously:
    # under load Storage.getCookies can run before it lands.
    async with asyncio.timeout(scaled(5)):
        while not (names := [c.name for c in await browser.get_cookies("127.0.0.1")]):
            await asyncio.sleep(0.05)
    assert names == ["seen"]
    await browser.clear_cookies("127.0.0.1")
    assert await tab.eval("document.cookie") == ""


async def test_context_cookies_are_isolated(browser):
    context = await browser.new_context()
    try:
        await context.set_cookies([Cookie(name="ctx", value="1", domain=".example.com")])
        await browser.set_cookies([Cookie(name="main", value="1", domain=".example.com")])
        assert _names(await context.get_cookies("example.com")) == ["ctx"]
        await browser.clear_cookies()
        assert _names(await context.get_cookies("example.com")) == ["ctx"]
    finally:
        await context.close()


async def test_context_get_cookies_matches_domain_not_substring(browser):
    context = await browser.new_context()
    try:
        await context.set_cookies(_JAR)
        assert _names(await context.get_cookies("example.com")) == ["a", "b"]
        assert _names(await context.get_cookies("notexample.com")) == ["c"]
    finally:
        await context.close()


async def test_context_clear_cookies_stays_in_the_context(browser):
    context = await browser.new_context()
    try:
        await context.set_cookies(_JAR)
        await browser.set_cookies([Cookie(name="main", value="1", domain=".example.com")])
        await context.clear_cookies("example.com")
        assert _names(await context.get_cookies()) == ["c", "d"]
        await context.clear_cookies()
        assert await context.get_cookies() == []
        assert _names(await browser.get_cookies()) == ["main"]
    finally:
        await context.close()


async def test_get_cookies_for_a_subdomain_includes_what_it_receives(browser):
    await browser.set_cookies(_JAR)
    assert _names(await browser.get_cookies("sub.example.com")) == ["a", "b"]


async def test_clear_cookies_for_a_subdomain_keeps_the_parent_domain(browser):
    await browser.set_cookies(_JAR)
    await browser.clear_cookies("sub.example.com")
    assert _names(await browser.get_cookies()) == ["a", "c", "d"]


async def test_a_public_suffix_does_not_return_everything(browser):
    await browser.set_cookies(_JAR)
    assert await browser.get_cookies("com") == []
    await browser.clear_cookies("com")
    assert _names(await browser.get_cookies()) == ["a", "b", "c", "d"]


async def test_an_intranet_host_without_a_dot(browser):
    await browser.set_cookies([*_JAR, Cookie(name="i", value="1", domain="intranet")])
    assert _names(await browser.get_cookies("intranet")) == ["i"]

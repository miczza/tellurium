"""robots.txt checks the URL Chrome navigates to, not a reading of its text (T8-B).

Two sites behind the local proxy: ``deny.test`` disallows everything,
``allow.test`` everything allowed. A URL Python and Chrome would read
differently (missing slashes, a backslash before ``@``, dot segments, tabs)
must be checked against the site Chrome really asks.
"""

from __future__ import annotations

import pytest

from tellurium import Browser, RobotsDisallowedError
from tests.integration.test_robots import TEXT, SiteProxy

pytestmark = pytest.mark.asyncio

DENY = b"User-agent: *\nDisallow: /\n"
ALLOW = b"User-agent: *\nDisallow:\n"

# Each goes to deny.test, path /p (or /@allow.test/p) in Chrome.
TO_DENY = [
    "http:deny.test/p",
    "http:/deny.test/p",
    "http:\\\\deny.test/p",
    "http://deny.test\\@allow.test/p",
    "HTTP://DENY.test/p",
    " http://deny.test/p",
    "ht\ttp://deny.\ntest/p",
    "http://deny.test/allow.test/../p",
]


@pytest.fixture
async def sites():
    routes = {
        "deny.test/robots.txt": (200, TEXT, DENY),
        "allow.test/robots.txt": (200, TEXT, ALLOW),
    }
    async with SiteProxy(routes) as proxy:
        browser = await Browser.launch(headless=True, proxy=proxy.url, respect_robots=True)
        try:
            yield proxy, browser
        finally:
            await browser.close()


def _requests(proxy: SiteProxy, host: str) -> list[str]:
    """The targets asked of *host*, robots.txt left out."""
    targets = [line.split(" ")[1] for line, _ in proxy.seen]
    return [t for t in targets if t.startswith(f"http://{host}/") and not t.endswith("/robots.txt")]


async def test_a_url_chrome_reads_as_the_denying_site_is_refused(sites):
    proxy, browser = sites
    tab = await browser.new_tab()
    for url in TO_DENY:
        with pytest.raises(RobotsDisallowedError) as caught:
            await tab.get(url, timeout=15)
        assert caught.value.origin == "http://deny.test", url
        assert not await tab.is_allowed(url), url
    assert _requests(proxy, "deny.test") == []


async def test_a_url_chrome_reads_as_the_allowing_site_is_let_through(sites):
    proxy, browser = sites
    tab = await browser.new_tab()
    url = "http://allow.test\\@deny.test/p"
    assert await tab.is_allowed(url)
    await tab.get(url, timeout=15)
    assert "http://allow.test/@deny.test/p" in _requests(proxy, "allow.test")
    assert _requests(proxy, "deny.test") == []


async def test_a_url_chrome_cannot_parse_is_not_allowed(sites):
    proxy, browser = sites
    tab = await browser.new_tab()
    for url in ("http://[deny.test/p", "http://", "http://deny.test:99999/p"):
        assert not await tab.is_allowed(url), url
        with pytest.raises(RobotsDisallowedError, match="not a URL"):
            await tab.get(url, timeout=15)
    assert [line for line, _ in proxy.seen if "deny.test" in line] == []

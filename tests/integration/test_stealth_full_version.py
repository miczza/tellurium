"""The full Chrome version a stealth page reports, in JS and in client hints.

Stealth launches Chrome with ``--user-agent=<profile UA>`` (T8-B, so robots.txt
leaves with the page's User-Agent). With that flag Chrome no longer fills the
full version on its own: every source of it must still agree.
"""

from __future__ import annotations

import json

import pytest

from tellurium import Browser
from tests.integration.test_robots import SiteProxy

pytestmark = pytest.mark.asyncio

ASK = {
    "Content-Type": "text/html",
    "Accept-CH": "Sec-CH-UA-Full-Version, Sec-CH-UA-Full-Version-List",
}
HIGH = "['uaFullVersion', 'fullVersionList']"
WORKER = (
    f"navigator.userAgentData.getHighEntropyValues({HIGH})"
    ".then(v => postMessage(JSON.stringify(v)))"
)
_IN_WORKER = (
    "new Promise(r => { const w = new Worker(URL.createObjectURL(new Blob(["
    + json.dumps(WORKER)
    + "]))); w.onmessage = e => r(e.data); })"
)


def _chrome(versions: list[dict]) -> str:
    return next(v["version"] for v in versions if v["brand"] == "Google Chrome")


@pytest.mark.parametrize("headless", [True, False], ids=["headless", "headed"])
async def test_the_full_version_is_the_same_everywhere(headless):
    routes = {p: (200, ASK, b"<!doctype html><p>ok") for p in ("/page", "/page2")}
    async with SiteProxy(routes) as site:  # straight from 127.0.0.1: a secure context
        browser = await Browser.launch(headless=headless, stealth=True)
        try:
            tab = await browser.new_tab()
            await tab.get(site.url + "/page", timeout=15)
            await tab.get(site.url + "/page2", timeout=15)  # Accept-CH now remembered
            page = json.loads(
                await tab.eval(f"navigator.userAgentData.getHighEntropyValues({HIGH})"
                               ".then(JSON.stringify)")
            )
            worker = json.loads(await tab.eval(_IN_WORKER))
            product = (await browser._router.root.send("Browser.getVersion", {}, timeout=10))[
                "product"
            ]
        finally:
            await browser.close()
    real = product.split("/", 1)[1]
    headers = {line.split(" ")[1]: h for line, h in site.seen}["/page2"]
    for values in (page, worker):
        assert values["uaFullVersion"] == real
        assert _chrome(values["fullVersionList"]) == real
    assert headers["sec-ch-ua-full-version"] == f'"{real}"'
    assert f'"Google Chrome";v="{real}"' in headers["sec-ch-ua-full-version-list"]

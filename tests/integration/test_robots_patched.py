"""robots.txt and the page with stealth on the patched backend (T8-B, round 4).

chromium-telluride produces User-Agent and client hints natively: tellurium sends
it no ``Emulation.setUserAgentOverride`` and must not launch it with
``--user-agent`` either, which would empty its native client hints and undo the
reduced User-Agent (``Chrome/146.0.0.0``).

Skipped unless a patched binary is available: ``TELLURIUM_PATCHED_EXECUTABLE``,
the sibling checkout ``../chromium-telluride/chromium-telluride/chrome``, or a
release in the cache.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tellurium import Browser
from tellurium.browser import _cache
from tests.integration.test_robots import ROBOTS, TEXT, SiteProxy
from tests.timeout_scale import scaled

pytestmark = pytest.mark.asyncio

_ROOT = Path(__file__).resolve().parents[2]
_SIBLING = Path("chromium-telluride", "chromium-telluride", "chrome")
ASK = {
    "Content-Type": "text/html",
    "Accept-CH": "Sec-CH-UA-Full-Version, Sec-CH-UA-Full-Version-List, Sec-CH-UA-Arch",
}
HIGH = "['uaFullVersion', 'fullVersionList', 'architecture']"


def _patched_binary() -> Path | None:
    env = os.environ.get("TELLURIUM_PATCHED_EXECUTABLE")
    candidates = [Path(env)] if env else []
    # The main checkout (../chromium-telluride) or a worktree of it (../../).
    candidates += [_ROOT.parent / _SIBLING, _ROOT.parent.parent / _SIBLING]
    candidates += [b.binary for b in _cache.installed_browsers()]
    return next((c for c in candidates if c.is_file()), None)


@pytest.fixture(scope="module")
def patched_binary() -> Path:
    binary = _patched_binary()
    if binary is None:
        pytest.skip(
            "no chromium-telluride binary (TELLURIUM_PATCHED_EXECUTABLE, "
            "../chromium-telluride/chromium-telluride/chrome or the cache)"
        )
    return binary


@pytest.mark.parametrize("headless", [True, False], ids=["headless", "headed"])
async def test_patched_stealth_keeps_its_native_user_agent_and_hints(patched_binary, headless):
    """No flag: robots.txt and the page leave with the binary's own User-Agent,
    reduced, and its high-entropy hints stay filled. (Headless, 146 still says
    ``HeadlessChrome``, as without stealth: docs/decisioni.md.)"""
    routes = {"/robots.txt": (200, TEXT, ROBOTS)}
    routes.update({p: (200, ASK, b"<!doctype html><p>ok") for p in ("/page", "/page2")})
    args = [] if (patched_binary.parent / "chrome_sandbox").is_file() else ["--no-sandbox"]
    async with SiteProxy(routes) as site:  # straight from 127.0.0.1: a secure context
        browser = await Browser.launch(
            browser="patched",
            executable=str(patched_binary),
            headless=headless,
            stealth=True,
            seed=7,
            args=args,
        )
        try:
            tab = await browser.new_tab()
            assert await tab.is_allowed(site.url + "/public")
            await tab.get(site.url + "/page", timeout=scaled(15))
            await tab.get(site.url + "/page2", timeout=scaled(15))  # Accept-CH now remembered
            main = await tab.eval("navigator.userAgent")
            high = json.loads(
                await tab.eval(
                    f"navigator.userAgentData.getHighEntropyValues({HIGH}).then(JSON.stringify)"
                )
            )
        finally:
            await browser.close()
    seen = {line.split(" ")[1]: h for line, h in site.seen}
    robots, page = seen["/robots.txt"], seen["/page2"]
    print(f"patched headless={headless} robots.txt UA:", robots["user-agent"])
    print(f"patched headless={headless} page UA:", page["user-agent"])
    assert "Chrome/146.0.0.0 " in main, main  # the reduced User-Agent
    assert page["user-agent"] == main
    assert high["uaFullVersion"] and high["fullVersionList"] and high["architecture"], high
    assert page.get("sec-ch-ua-full-version-list"), page
    assert robots["user-agent"] == page["user-agent"]

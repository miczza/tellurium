"""Integration: T7 runtime script injection on stock Chrome branded."""

from __future__ import annotations

import os
import shutil

import pytest

from tellurium import Browser

pytestmark = pytest.mark.stealth

STOCK_CHROME = os.environ.get("STOCK_CHROME", "/usr/bin/google-chrome-stable")


@pytest.mark.skipif(
    not shutil.which(STOCK_CHROME) and not os.path.exists(STOCK_CHROME),
    reason="Stock Chrome not installed",
)
@pytest.mark.asyncio
async def test_runtime_injection_hides_webdriver_on_branded_chrome():
    """On Chrome branded >=137, --load-extension is rejected. T7 must still
    hide navigator.webdriver via Page.addScriptToEvaluateOnNewDocument."""
    browser = await Browser.launch(
        headless=True,
        stealth=True,
        executable=STOCK_CHROME,
    )
    try:
        tab = await browser.new_tab("about:blank")
        wd = await tab.eval("navigator.webdriver")
        assert wd is None or wd is False, f"navigator.webdriver = {wd!r}"

        # window.chrome should exist (from chrome_runtime.js)
        has_chrome = await tab.eval("typeof window.chrome === 'object'")
        assert has_chrome is True

        # Plugins list must be non-empty (from plugins.js)
        plugins_len = await tab.eval("navigator.plugins.length")
        assert plugins_len > 0
    finally:
        await browser.close()


@pytest.mark.skipif(
    not shutil.which(STOCK_CHROME) and not os.path.exists(STOCK_CHROME),
    reason="Stock Chrome not installed",
)
@pytest.mark.asyncio
async def test_runtime_injection_survives_navigation():
    """The override must persist across navigations (runImmediately + persistent)."""
    browser = await Browser.launch(
        headless=True,
        stealth=True,
        executable=STOCK_CHROME,
    )
    try:
        tab = await browser.new_tab("about:blank")
        await tab.get("data:text/html,<html><body>nav1</body></html>")
        wd1 = await tab.eval("navigator.webdriver")
        await tab.get("data:text/html,<html><body>nav2</body></html>")
        wd2 = await tab.eval("navigator.webdriver")
        assert wd1 is None or wd1 is False
        assert wd2 is None or wd2 is False
    finally:
        await browser.close()

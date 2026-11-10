"""Navigation waits, page title, and tab lifecycle (popups, close, contexts)."""

from __future__ import annotations

import asyncio

import pytest

from tests.timeout_scale import scaled

# ---------------------------------------------------------------------------
# Tab.get(wait_until=...)
# ---------------------------------------------------------------------------


async def test_domcontentloaded_does_not_wait_for_subresources(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/slow_load.html", wait_until="domcontentloaded")
    assert await tab.eval("document.readyState") != "complete"


async def test_load_waits_for_subresources(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/slow_load.html", wait_until="load")
    assert await tab.eval("document.readyState") == "complete"


async def test_networkidle_waits_for_requests_after_load(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/late_fetch.html", wait_until="networkidle")
    assert await tab.eval("window.lateDone") is True


async def test_same_document_navigation_returns(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")
    await tab.get(f"{local_server}/basic.html#section", timeout=scaled(5))
    assert await tab.eval("location.hash") == "#section"


async def test_unknown_wait_until_is_rejected(browser, local_server):
    with pytest.raises(ValueError, match="wait_until"):
        await browser.main_tab.get(f"{local_server}/basic.html", wait_until="idle")


# ---------------------------------------------------------------------------
# Tab.title / Tab.url
# ---------------------------------------------------------------------------


async def test_title_is_the_loaded_document_title(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    assert tab.title == "Basic Test Page"


async def test_url_is_the_final_url_after_a_redirect(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/redirect/basic.html")
    assert tab.url == f"{local_server}/basic.html"


async def test_url_follows_in_page_navigation(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    await tab.eval("location.href = '/tree.html'; 1")
    await tab.wait_for_url("*/tree.html", timeout=scaled(5))
    assert tab.url.endswith("/tree.html")


# ---------------------------------------------------------------------------
# Popups
# ---------------------------------------------------------------------------


async def _click_popup_link(tab):
    link = await tab.select("#pop")
    box = await link.bounding_box()
    await tab.mouse_click(box["x"] + 10, box["y"] + 10)


async def test_popup_is_tracked_and_usable(browser, local_server):
    opener = await browser.new_tab(f"{local_server}/opener.html")
    await _click_popup_link(opener)

    popup = await browser.wait_for_tab("*/popup_target.html", timeout=scaled(10))

    assert popup in browser.tabs
    assert popup is not opener
    msg = await popup.select("#msg")
    assert await msg.text() == "I am the popup"


async def test_popup_gets_stealth_before_its_own_scripts(stealth_browser, local_server):
    opener = await stealth_browser.new_tab(f"{local_server}/opener.html")
    await _click_popup_link(opener)

    popup = await stealth_browser.wait_for_tab("*/popup_target.html", timeout=scaled(10))
    await popup.wait_for("#msg", state="attached", timeout=scaled(10))

    assert await popup.eval("window.__webdriverAtStart") is False


async def test_new_tab_gets_stealth_before_its_own_scripts(stealth_browser, local_server):
    tab = await stealth_browser.new_tab(f"{local_server}/popup_target.html")
    assert await tab.eval("window.__webdriverAtStart") is False


async def test_context_tab_gets_stealth_before_its_own_scripts(stealth_browser, local_server):
    ctx = await stealth_browser.new_context()
    tab = await ctx.new_tab(f"{local_server}/popup_target.html")
    await tab.wait_for("#msg", state="attached", timeout=scaled(10))
    assert await tab.eval("window.__webdriverAtStart") is False
    assert tab in ctx.tabs


# ---------------------------------------------------------------------------
# Closing
# ---------------------------------------------------------------------------


async def test_tab_close_removes_the_tab(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    await tab.close()

    assert tab not in browser.tabs
    targets = await browser._router.root.send("Target.getTargets", {})
    assert tab._target_id not in {t["targetId"] for t in targets["targetInfos"]}


async def test_tab_closed_by_the_page_is_dropped(browser, local_server):
    opener = await browser.new_tab(f"{local_server}/opener.html")
    await _click_popup_link(opener)
    popup = await browser.wait_for_tab("*/popup_target.html", timeout=scaled(10))

    await popup.eval("window.close(); 1")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + scaled(5)
    while popup in browser.tabs and loop.time() < deadline:
        await asyncio.sleep(0.1)
    assert popup not in browser.tabs

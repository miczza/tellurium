"""Element handles do not pin DOM nodes (R1: M4, m6, m9 stale elements)."""

from __future__ import annotations

import asyncio
import gc
from urllib.parse import quote

import pytest

from tellurium.browser.handles import StaleElementError
from tellurium.cdp.types import CDPError
from tests.timeout_scale import scaled

GUARD = 60

FEED = "data:text/html," + quote(
    "<html><body><div id='feed'></div><script>"
    "window.fill = () => { const f = document.getElementById('feed');"
    "  for (let i = 0; i < 300; i++) {"
    "    const d = document.createElement('div'); d.className = 'row';"
    "    d.textContent = 'line' + '#' + i; f.appendChild(d); } return 1; };"
    "window.clear = () => { document.getElementById('feed').replaceChildren(); return 1; };"
    "</script></body></html>"
)


async def _live_nodes(tab) -> int:
    await tab.send_cdp("HeapProfiler.collectGarbage")
    counters = await tab.send_cdp("Memory.getDOMCounters")
    return counters["nodes"]


async def _settle(tab) -> None:
    gc.collect()
    await tab._handles.drain()


async def _cycles(tab, query, rounds: int = 20) -> None:
    for _ in range(rounds):
        await tab.eval("fill()")
        found = await query()
        assert len(found) == 300
        del found
        await tab.eval("clear()")


async def test_dropped_query_results_do_not_keep_removed_nodes_alive(browser):
    async def body():
        tab = browser.main_tab
        await tab.get(FEED)
        baseline = await _live_nodes(tab)
        await _cycles(tab, lambda: tab.select_all(".row"))
        await _settle(tab)
        # 20 rounds x 300 rows x 2 nodes would be ~12000 if handles leaked.
        assert await _live_nodes(tab) - baseline < 1500

    await asyncio.wait_for(body(), timeout=scaled(GUARD))


async def test_dropped_text_query_results_are_released_too(browser):
    async def body():
        tab = browser.main_tab
        await tab.get(FEED)
        baseline = await _live_nodes(tab)
        await _cycles(tab, lambda: tab.find_all("line#"))
        await _settle(tab)
        assert await _live_nodes(tab) - baseline < 1500

    await asyncio.wait_for(body(), timeout=scaled(GUARD))


async def test_released_element_raises_stale_element_error(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")
    heading = await tab.select("h1")
    object_id = heading._object_id
    await heading.release()
    with pytest.raises(StaleElementError):
        await heading.text()
    with pytest.raises(CDPError):
        await tab.send_cdp("Runtime.getProperties", {"objectId": object_id})
    await heading.release()  # idempotent


async def test_element_from_a_previous_document_is_stale(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")
    heading = await tab.select("h1")
    await tab.get(f"{local_server}/form.html")
    with pytest.raises(StaleElementError) as info:
        await heading.text()
    assert isinstance(info.value, CDPError)


async def test_navigation_rotates_the_object_group(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")
    before = tab._handles.name
    await tab.get(f"{local_server}/form.html")
    assert tab._handles.name != before
    heading = await tab.select("form")
    assert await heading.tag() == "form"


async def test_kept_elements_stay_usable(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")
    heading = await tab.select("h1")
    for _ in range(5):
        await tab.select_all("p")
    await _settle(tab)
    assert await heading.tag() == "h1"


async def test_element_call_is_bounded_while_a_dialog_is_open(browser, local_server, monkeypatch):
    from tellurium.browser import handles

    monkeypatch.setattr(handles, "HANDLE_TIMEOUT", 1.0, raising=False)
    tab = browser.main_tab
    tab._dialogs.policy = "manual"
    await tab.get(f"{local_server}/basic.html")
    heading = await tab.select("h1")
    await tab.eval("setTimeout(() => alert('stuck'), 0); 1")
    await asyncio.sleep(0.3)
    with pytest.raises(TimeoutError, match="Runtime.callFunctionOn"):
        await asyncio.wait_for(heading.text(), timeout=scaled(10))
    await tab._dialogs.last.dismiss()
    assert await heading.tag() == "h1"


async def test_close_is_not_delayed_by_a_frozen_page(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    tab._dialogs.policy = "manual"
    await tab.select("h1")
    await tab.eval("setTimeout(() => alert('stuck'), 0); 1")
    await asyncio.sleep(0.3)
    loop = asyncio.get_running_loop()
    start = loop.time()
    await asyncio.wait_for(tab.close(), timeout=scaled(15))
    assert loop.time() - start < 2.5
    assert tab.closed

"""Tab.wait_for_human: a banner in a closed shadow root, "Done" only from a real
(CDP-dispatched) click, a URL glob or an async condition, a timeout, nothing
left in the DOM."""

from __future__ import annotations

import asyncio
import os

import pytest

HEADED = bool(os.environ.get("DISPLAY"))
needs_display = pytest.mark.skipif(not HEADED, reason="needs a display (xvfb-run)")


@pytest.fixture
async def headed():
    from tellurium import Browser

    b = await Browser.launch(headless=False)
    yield b
    await b.close()


def _walk(node):
    yield node
    for child in node.get("children", []):
        yield from _walk(child)
    for root in node.get("shadowRoots", []):
        yield from _walk(root)


async def _closed_roots(tab) -> list[dict]:
    """The closed shadow roots of the page (CDP sees through them)."""
    doc = await tab.send_cdp("DOM.getDocument", {"depth": -1, "pierce": True})
    return [n for n in _walk(doc["root"]) if n.get("shadowRootType") == "closed"]


async def _done_button(tab, timeout: float = 10) -> int:
    """The nodeId of the banner's button, once the banner is there."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        for root in await _closed_roots(tab):
            for node in _walk(root):
                if node.get("nodeName") == "BUTTON":
                    return node["nodeId"]
        if loop.time() > deadline:
            raise AssertionError("no banner button appeared")
        await asyncio.sleep(0.1)


async def _click_node(tab, node_id: int) -> None:
    quad = (await tab.send_cdp("DOM.getBoxModel", {"nodeId": node_id}))["model"]["content"]
    x = (quad[0] + quad[2] + quad[4] + quad[6]) / 4
    y = (quad[1] + quad[3] + quad[5] + quad[7]) / 4
    await tab.mouse_click(x, y)


async def _until_settled(task, seconds: float) -> bool:
    """Whether *task* finished within *seconds*."""
    done, _ = await asyncio.wait({task}, timeout=seconds)
    return bool(done)


@needs_display
async def test_a_real_click_on_done_returns_and_leaves_no_node(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/basic.html")
    before = await tab.eval("document.documentElement.outerHTML")
    globals_before = await tab.eval("Object.getOwnPropertyNames(window).sort().join(',')")
    task = asyncio.create_task(tab.wait_for_human("Solve the captcha", timeout=30))
    try:
        button = await _done_button(tab)
        text = await tab.eval("document.body.innerText")
        assert "Solve the captcha" not in text  # the page cannot read the banner
        globals_during = await tab.eval("Object.getOwnPropertyNames(window).sort().join(',')")
        assert globals_during == globals_before  # no binding in the page's world
        await _click_node(tab, button)
        assert await _until_settled(task, 5)
        await task
    finally:
        task.cancel()
    assert await _closed_roots(tab) == []
    assert await tab.eval("document.documentElement.outerHTML") == before


@needs_display
async def test_a_click_from_the_page_does_not_count(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/basic.html")
    task = asyncio.create_task(tab.wait_for_human("Sign in", timeout=4))
    try:
        button = await _done_button(tab)
        # The page, even holding the button itself, can only make untrusted clicks.
        obj = (await tab.send_cdp("DOM.resolveNode", {"nodeId": button}))["object"]
        await tab.send_cdp(
            "Runtime.callFunctionOn",
            {
                "objectId": obj["objectId"],
                "functionDeclaration": "function () { this.click();"
                " this.dispatchEvent(new MouseEvent('click', {bubbles: true})); }",
            },
        )
        await tab.eval("document.documentElement.lastElementChild.click()")
        assert not await _until_settled(task, 1.5)
        with pytest.raises(TimeoutError):
            await task
    finally:
        task.cancel()
    assert await _closed_roots(tab) == []


@needs_display
async def test_the_banner_comes_back_after_a_navigation(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/basic.html")
    task = asyncio.create_task(tab.wait_for_human("Go on", timeout=30))
    try:
        await _done_button(tab)
        await tab.get(f"{local_server}/form.html")
        button = await _done_button(tab)
        await _click_node(tab, button)
        assert await _until_settled(task, 5)
        await task
    finally:
        task.cancel()


@needs_display
async def test_done_works_after_a_cross_process_navigation_as_the_wait_starts(local_server):
    """The person leaves Chrome's first page (another renderer) while the banner
    is being set up: world and binding must still end up in the same document."""
    from tellurium import Browser

    for _ in range(3):
        browser = await Browser.launch(headless=False)
        try:
            tab = browser.main_tab
            task = asyncio.create_task(tab.wait_for_human("Go on", timeout=20))
            try:
                await tab.get(f"{local_server}/basic.html")
                await _click_node(tab, await _done_button(tab))
                assert await _until_settled(task, 5)
                await task
            finally:
                task.cancel()
        finally:
            await browser.close()


@needs_display
async def test_the_banner_comes_back_when_the_page_removes_it(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/basic.html")
    task = asyncio.create_task(tab.wait_for_human("Go on", timeout=30))
    try:
        await _done_button(tab)
        await tab.eval("document.documentElement.lastElementChild.remove()")
        await _click_node(tab, await _done_button(tab))
        assert await _until_settled(task, 5)
        await task
    finally:
        task.cancel()


@needs_display
async def test_a_url_glob_ends_the_wait_in_headed_too(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/basic.html")
    task = asyncio.create_task(tab.wait_for_human("Sign in", until="*/dashboard*", timeout=30))
    try:
        await _done_button(tab)
        await tab.get(f"{local_server}/dashboard.html")
        assert await _until_settled(task, 5)
        await task
    finally:
        task.cancel()
    assert await _closed_roots(tab) == []


async def test_headless_waits_for_the_url_glob_with_no_banner(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")
    task = asyncio.create_task(tab.wait_for_human("Sign in", until="**/dashboard*", timeout=30))
    try:
        await asyncio.sleep(0.5)
        assert not task.done()
        assert await _closed_roots(tab) == []
        await tab.eval("location.href = '/dashboard.html'")
        assert await _until_settled(task, 5)
        await task
    finally:
        task.cancel()


async def test_an_async_condition_ends_the_wait(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")
    seen = []

    async def submitted(t):
        seen.append(t)
        return await t.eval("document.getElementById('content').textContent") == "submitted"

    task = asyncio.create_task(tab.wait_for_human("Submit", until=submitted, timeout=30))
    try:
        await asyncio.sleep(0.5)
        assert not task.done()
        await tab.eval("document.getElementById('submit').click()")
        assert await _until_settled(task, 5)
        await task
    finally:
        task.cancel()
    assert seen and seen[0] is tab


async def test_the_timeout_raises(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")
    loop = asyncio.get_running_loop()
    start = loop.time()
    with pytest.raises(TimeoutError, match="Sign in"):
        await tab.wait_for_human("Sign in", until="*/never*", timeout=1)
    assert loop.time() - start < 5


async def test_headless_without_a_condition_is_refused(any_browser):
    with pytest.raises(ValueError, match="until"):
        await any_browser.main_tab.wait_for_human("Sign in")


async def test_a_condition_of_the_wrong_type_is_refused(browser):
    with pytest.raises(TypeError, match="until"):
        await browser.main_tab.wait_for_human("Sign in", until=42)


# --- A page that fights the banner -------------------------------------------


async def _click_done_until_it_ends(tab, task, seconds: float = 6) -> None:
    """Click where the banner's button is, again and again, until *task* ends:
    the banner may need a round or two to come back from what the page did."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while not task.done():
        if loop.time() > deadline:
            raise AssertionError("Done never ended the wait")
        try:
            await _click_node(tab, await _done_button(tab))
        except Exception:  # noqa: BLE001 - hidden (no box) or rebuilt meanwhile
            pass
        await _until_settled(task, 0.4)
    await task


async def _on_top(tab) -> bool:
    """Whether the banner's button is what a click at its centre would hit."""
    obj = (await tab.send_cdp("DOM.resolveNode", {"nodeId": await _done_button(tab)}))["object"]
    hit = await tab.send_cdp(
        "Runtime.callFunctionOn",
        {
            "objectId": obj["objectId"],
            "functionDeclaration": "function () { const r = this.getBoundingClientRect();"
            " if (!r.width || !r.height) return false;"
            " const x = r.left + r.width / 2, y = r.top + r.height / 2;"
            " return this.getRootNode().elementFromPoint(x, y) === this; }",
            "returnByValue": True,
        },
    )
    return hit["result"]["value"]


@needs_display
async def test_done_survives_a_page_that_hides_the_banner(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/human_hide.html")  # html > div {display: none !important}
    task = asyncio.create_task(tab.wait_for_human("Go on", timeout=30))
    try:
        await _done_button(tab)
        await tab.eval("hideBanner()")  # an inline display:none !important on the host
        await _click_done_until_it_ends(tab, task)
    finally:
        task.cancel()


@needs_display
async def test_done_survives_capture_listeners_that_stop_every_click(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/human_capture.html")
    task = asyncio.create_task(tab.wait_for_human("Go on", timeout=30))
    try:
        await _click_done_until_it_ends(tab, task)
    finally:
        task.cancel()


@needs_display
async def test_done_survives_clicks_cancelled_by_a_page_loaded_during_the_wait(
    headed, local_server
):
    tab = headed.main_tab
    await tab.get(f"{local_server}/basic.html")
    task = asyncio.create_task(tab.wait_for_human("Go on", timeout=30))
    try:
        await _done_button(tab)
        await tab.get(f"{local_server}/human_cancel.html")  # preventDefault on every click
        await _click_done_until_it_ends(tab, task)
    finally:
        task.cancel()


@needs_display
async def test_done_stays_clickable_over_a_modal_dialog(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/human_modal.html")  # showModal() on load
    task = asyncio.create_task(tab.wait_for_human("Go on", timeout=30))
    try:
        await _done_button(tab)
        await tab.eval("reopen()")  # the page's dialog back on top of the banner
        await _click_done_until_it_ends(tab, task)
    finally:
        task.cancel()


@needs_display
async def test_the_banner_keeps_its_style_under_a_style_src_csp(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/human_csp.html")  # style-src 'none'
    task = asyncio.create_task(tab.wait_for_human("Go on", timeout=30))
    try:
        obj = await tab.send_cdp("DOM.resolveNode", {"nodeId": await _done_button(tab)})
        style = await tab.send_cdp(
            "Runtime.callFunctionOn",
            {
                "objectId": obj["object"]["objectId"],
                "functionDeclaration": "function () { return getComputedStyle(this)"
                ".backgroundColor; }",
                "returnByValue": True,
            },
        )
        assert style["result"]["value"] == "rgb(62, 189, 147)"
        assert await _on_top(tab)
    finally:
        task.cancel()


async def test_headless_is_told_apart_even_with_a_user_agent_of_headed_chrome():
    """--user-agent rewrites the user agent Browser.getVersion reports, not its product."""
    from tellurium import Browser

    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0"
    b = await Browser.launch(headless=True, args=[f"--user-agent={ua}"])
    try:
        with pytest.raises(ValueError, match="until"):
            await asyncio.wait_for(b.main_tab.wait_for_human("Sign in", timeout=3), 10)
    finally:
        await b.close()


@pytest.mark.parametrize("pattern", ["**/dashboard*", "/dashboard"])
async def test_the_url_pattern_ignores_query_and_fragment(browser, local_server, pattern):
    """A sign-in page naming where it goes next (?next=/dashboard, #/dashboard)
    is not the dashboard."""
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html?next=/dashboard")
    task = asyncio.create_task(tab.wait_for_human("Sign in", until=pattern, timeout=30))
    try:
        assert not await _until_settled(task, 0.8)
        await tab.eval("location.hash = '#/dashboard'")
        assert not await _until_settled(task, 0.8)
        await tab.eval("location.href = '/dashboard.html?from=/login#top'")
        assert await _until_settled(task, 5)
        await task
    finally:
        task.cancel()

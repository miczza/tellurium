"""JavaScript dialogs never block the tab (R1, M2).

Every test runs under an outer guard: before the fix a dialog froze every
later command forever, so a regression must fail fast instead of hanging.
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote

from tests.timeout_scale import scaled

GUARD = 15


def _page(body: str) -> str:
    return "data:text/html," + quote(f"<html><body>{body}</body></html>")


async def _guard(coro):
    return await asyncio.wait_for(coro, timeout=scaled(GUARD))


async def test_alert_on_load_does_not_block_get_or_later_commands(browser):
    tab = browser.main_tab
    url = _page("<script>window.onload = () => alert('hi')</script>")
    await _guard(tab.get(url, wait_until="load", timeout=scaled(8)))
    assert await _guard(tab.eval("1 + 1")) == 2


async def test_alert_after_domcontentloaded_does_not_block_the_next_call(browser):
    tab = browser.main_tab
    url = _page("<script>setTimeout(() => alert('later'), 50)</script>")
    await _guard(tab.get(url, wait_until="domcontentloaded", timeout=scaled(8)))
    await asyncio.sleep(0.3)
    assert await _guard(tab.eval("document.body !== null")) is True


async def test_alert_from_eval_is_dismissed_and_eval_returns(browser):
    tab = browser.main_tab
    await _guard(tab.get(_page("<p>x</p>")))
    assert await _guard(tab.eval("alert('x'); 5")) == 5


async def test_confirm_is_dismissed_by_default(browser):
    tab = browser.main_tab
    await _guard(tab.get(_page("<p>x</p>")))
    assert await _guard(tab.eval("confirm('sure?')")) is False


async def test_on_dialog_handler_can_accept_a_prompt_with_text(browser):
    tab = browser.main_tab
    seen = []

    async def handler(dialog):
        seen.append((dialog.type, dialog.message))
        await dialog.accept("Bob")

    tab.on_dialog(handler)
    await _guard(tab.get(_page("<p>x</p>")))
    assert await _guard(tab.eval("prompt('name?')")) == "Bob"
    assert seen == [("prompt", "name?")]


async def test_sync_handler_that_does_not_decide_falls_back_to_the_policy(browser):
    tab = browser.main_tab
    seen = []
    tab.on_dialog(lambda dialog: seen.append(dialog.type))
    await _guard(tab.get(_page("<p>x</p>")))
    assert await _guard(tab.eval("confirm('ok?')")) is False
    assert seen == ["confirm"]


async def test_failing_handler_still_closes_the_dialog(browser):
    tab = browser.main_tab

    def handler(dialog):
        raise ValueError("boom")

    tab.on_dialog(handler)
    await _guard(tab.get(_page("<p>x</p>")))
    assert await _guard(tab.eval("confirm('ok?')")) is False


async def test_accept_policy_accepts_confirm(browser):
    tab = browser.main_tab
    tab._dialogs.policy = "accept"
    await _guard(tab.get(_page("<p>x</p>")))
    assert await _guard(tab.eval("confirm('sure?')")) is True


async def test_dialogs_on_a_new_tab_are_handled(browser):
    tab = await _guard(browser.new_tab(_page("<p>x</p>")))
    assert await _guard(tab.eval("confirm('sure?')")) is False


async def test_handler_can_be_removed(browser):
    tab = browser.main_tab
    seen = []
    tab.on_dialog(lambda dialog: seen.append(dialog.type))
    tab.on_dialog(None)
    await _guard(tab.get(_page("<p>x</p>")))
    await _guard(tab.eval("alert('x')"))
    assert seen == []


async def test_beforeunload_is_accepted_so_navigation_proceeds(browser):
    tab = browser.main_tab
    seen = []
    tab.on_dialog(lambda dialog: seen.append(dialog.type))
    page = _page(
        "<p style='height:200px'>x</p><script>"
        "addEventListener('beforeunload', e => { e.preventDefault(); e.returnValue = ''; });"
        "</script>"
    )
    await _guard(tab.get(page))
    await _guard(tab.mouse_click(20, 20))  # beforeunload needs a user gesture
    await _guard(tab.get(_page("<p id='next'>next</p>"), timeout=scaled(8)))
    assert seen == ["beforeunload"]
    assert await _guard(tab.eval("document.getElementById('next') !== null")) is True


async def test_handler_that_never_decides_times_out_to_the_policy(browser):
    tab = browser.main_tab
    tab._dialogs.handler_timeout = 0.5

    async def handler(dialog):
        await asyncio.sleep(3600)

    tab.on_dialog(handler)
    await _guard(tab.get(_page("<p>x</p>")))
    assert await asyncio.wait_for(tab.eval("confirm('ok?')"), timeout=scaled(5)) is False


async def test_launch_dialog_policy_reaches_every_tab():
    from tellurium import Browser

    browser = await Browser.launch(headless=True, dialogs="accept")
    try:
        main = browser.main_tab
        await _guard(main.get(_page("<p>x</p>")))
        assert await _guard(main.eval("confirm('sure?')")) is True
        other = await _guard(browser.new_tab(_page("<p>y</p>")))
        assert await _guard(other.eval("confirm('sure?')")) is True
    finally:
        await browser.close()


async def test_alert_on_the_initial_tab_before_any_get_is_dismissed(browser):
    tab = browser.main_tab
    assert await _guard(tab.eval("alert('early'); 7", timeout=scaled(5))) == 7


async def test_unknown_launch_dialog_policy_is_refused_before_chrome_starts():
    import pytest

    from tellurium import Browser

    with pytest.raises(ValueError, match="dialog"):
        await Browser.launch(headless=True, executable="/nonexistent/chrome", dialogs="ignore")

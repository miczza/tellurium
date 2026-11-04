"""Tab.wait_for_human at its edges: one deadline on a busy page, the early
script taken away however the wait ends, documents that are not HTML, and a
profile that goes from headless to headed."""

from __future__ import annotations

import asyncio
import logging

import pytest

from tests.integration.test_wait_for_human import (
    _click_done_until_it_ends,
    _closed_roots,
    _done_button,
    headed,  # noqa: F401 - fixture
    needs_display,
)


def _spy(tab, monkeypatch) -> list[tuple[str, dict, object]]:
    """Every command *tab*'s session sends: ``(method, params, reply)``."""
    sent: list[tuple[str, dict, object]] = []
    real_send = tab._session.send

    async def spy(method, params=None, timeout=None):
        entry = [method, params or {}, None]
        sent.append(entry)
        entry[2] = await real_send(method, params, timeout=timeout)
        return entry[2]

    monkeypatch.setattr(tab._session, "send", spy)
    return sent


async def _late_script_removed(sent, seconds: float) -> bool:
    """Whether the early script's identifier, once Chrome gives it, is taken away."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        added = [r for m, _, r in sent if m == "Page.addScriptToEvaluateOnNewDocument" and r]
        removed = [p for m, p, _ in sent if m == "Page.removeScriptToEvaluateOnNewDocument"]
        if added and {"identifier": added[0]["identifier"]} in removed:
            return True
        await asyncio.sleep(0.1)
    return False


# --- One deadline ---------------------------------------------------------------


@needs_display
async def test_the_timeout_holds_on_a_page_busy_in_long_ticks(headed, local_server):  # noqa: F811
    """Every CDP call takes at most what is left of the wait, the banner's
    cleanup included."""
    tab = headed.main_tab
    await tab.get(f"{local_server}/human_ticks.html")
    await tab.eval("ticks(2000)")
    await asyncio.sleep(0.3)
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        with pytest.raises(TimeoutError, match="within 3 s"):
            await tab.wait_for_human("Go on", timeout=3)
        assert loop.time() - started < 4
    finally:
        await tab.eval("stop()")


async def test_a_condition_on_a_busy_page_keeps_the_deadline(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/human_ticks.html")
    await tab.eval("ticks(2000)")
    await asyncio.sleep(0.3)

    async def signed_in(t) -> bool:
        return bool(await t.eval("document.cookie.includes('sso=')"))

    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        with pytest.raises(TimeoutError, match="within 3 s"):
            await tab.wait_for_human("Sign in", until=signed_in, timeout=3)
        assert loop.time() - started < 4
    finally:
        await tab.eval("stop()")


async def test_expiring_inside_the_condition_names_the_timeout(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")

    async def never(t) -> bool:
        await asyncio.sleep(3600)
        return True

    with pytest.raises(TimeoutError, match=r"'Sign in'.*within 1 s"):
        await tab.wait_for_human("Sign in", until=never, timeout=1)


# --- The early script ------------------------------------------------------------


@needs_display
async def test_an_early_script_registered_after_the_wait_is_taken_away(
    headed,  # noqa: F811
    local_server,
    monkeypatch,
):
    """Chrome answers Page.addScriptToEvaluateOnNewDocument only once the page
    is free: if that is after the wait, the script goes as soon as it is known."""
    tab = headed.main_tab
    await tab.get(f"{local_server}/human_busy.html")
    sent = _spy(tab, monkeypatch)
    await tab.eval("busy(4000)")
    await asyncio.sleep(0.3)
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(TimeoutError):
        await tab.wait_for_human("Go on", timeout=1)
    assert loop.time() - started < 2
    assert await _late_script_removed(sent, 10)


@needs_display
async def test_a_cancelled_close_still_takes_the_late_script_away(
    headed,  # noqa: F811
    local_server,
    monkeypatch,
):
    tab = headed.main_tab
    await tab.get(f"{local_server}/human_busy.html")
    sent = _spy(tab, monkeypatch)
    await tab.eval("busy(4000)")
    await asyncio.sleep(0.3)
    task = asyncio.create_task(tab.wait_for_human("Go on", timeout=30))
    await asyncio.sleep(0.5)
    task.cancel()
    await asyncio.sleep(0.05)  # in the cleanup now
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await _late_script_removed(sent, 10)
    await tab.get(f"{local_server}/form.html")
    await asyncio.sleep(0.5)
    assert await _closed_roots(tab) == []


# --- Documents that are not HTML -------------------------------------------------


@needs_display
@pytest.mark.parametrize("name", ["human.svg", "human.xml"])
async def test_done_works_on_a_document_that_is_not_html(headed, local_server, name):  # noqa: F811
    tab = headed.main_tab
    await tab.get(f"{local_server}/{name}")
    task = asyncio.create_task(tab.wait_for_human("Go on", timeout=30))
    try:
        await _done_button(tab)
        await _click_done_until_it_ends(tab, task)
    finally:
        task.cancel()
    assert await _closed_roots(tab) == []


@needs_display
async def test_a_banner_that_fails_says_why(headed, local_server, monkeypatch, caplog):  # noqa: F811
    from tellurium.browser import human

    broken = "(function (a, b, c) { throw new Error('banner broke'); })(%s, %s, %s)"
    monkeypatch.setattr(human, "_SHOW_JS", broken)
    tab = headed.main_tab
    await tab.get(f"{local_server}/basic.html")
    with caplog.at_level(logging.WARNING, logger="tellurium"):
        with pytest.raises(TimeoutError):
            await tab.wait_for_human("Go on", timeout=1.5)
    assert sum("banner broke" in r.getMessage() for r in caplog.records) == 1


# --- From headless to headed -----------------------------------------------------


@needs_display
async def test_a_cookie_set_headless_is_there_headed_on_the_same_profile(tmp_path, local_server):
    """Sign-in fails headless, the same profile opens headed for a person: what
    the headless run stored is still there."""
    from tellurium import Browser

    profile = str(tmp_path / "profile")
    b = await Browser.launch(headless=True, user_data_dir=profile)
    try:
        await b.main_tab.get(f"{local_server}/basic.html")
        await b.main_tab.eval("document.cookie = 'sso=1; max-age=3600; path=/'")
        # The renderer hands the cookie to the browser's store asynchronously: wait for
        # it to land before closing, or a loaded machine closes first.
        async with asyncio.timeout(5):
            while not await b.get_cookies("127.0.0.1"):
                await asyncio.sleep(0.05)
    finally:
        await b.close()
    b = await Browser.launch(headless=False, user_data_dir=profile)
    try:
        await b.main_tab.get(f"{local_server}/basic.html")
        assert "sso=1" in await b.main_tab.eval("document.cookie")
    finally:
        await b.close()


# --- Closing the browser mid-wait ------------------------------------------------


def _other_tasks() -> set[asyncio.Task]:
    return asyncio.all_tasks() - {asyncio.current_task()}


async def _settled(seconds: float = 2) -> set[asyncio.Task]:
    """The tasks still there once those that are ending have ended."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while _other_tasks() and loop.time() < deadline:
        await asyncio.sleep(0.01)
    return _other_tasks()


@needs_display
async def test_closing_the_browser_mid_wait_leaves_no_task(local_server):
    """The late early script's reply and the cleanup are awaited in the
    background with no clock of their own: the browser that owns them ends
    them when it closes."""
    from tellurium import Browser

    b = await Browser.launch(headless=False)
    try:
        tab = b.main_tab
        await tab.get(f"{local_server}/human_busy.html")
        await tab.eval("busy(4000)")
        await asyncio.sleep(0.3)
        task = asyncio.create_task(tab.wait_for_human("Go on", timeout=30))
        await asyncio.sleep(0.5)
    finally:
        await asyncio.wait_for(b.close(), 15)
    with pytest.raises(ConnectionError):
        await asyncio.wait_for(task, 5)
    assert await _settled() == set()

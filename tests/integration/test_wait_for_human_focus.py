"""The banner's "Done" on a tab whose window is not the focused one (another
window of Chrome, or of another program, came up after it): a person sees
the tab brought to the front, and the click lands."""

from __future__ import annotations

import asyncio
import sys

import pytest

from tests.integration import banner_probe
from tests.integration.test_wait_for_human import _click_node, _done_button, _until_settled
from tests.platform_marks import needs_display


@pytest.fixture
async def headed():
    from tellurium import Browser

    b = await Browser.launch(headless=False)
    yield b
    await b.close()


async def _focus_elsewhere(browser) -> None:
    """Open another window of Chrome, which takes the focus from the first."""
    root = browser._router.root
    await root.send("Target.createTarget", {"url": "about:blank", "newWindow": True}, timeout=10)


async def _has_focus(tab, timeout: float = 5) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if await tab.eval("document.hasFocus()"):
            return True
        await asyncio.sleep(0.1)
    return False


@needs_display
async def test_done_lands_on_a_tab_whose_window_lost_the_focus(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/basic.html")
    await _focus_elsewhere(headed)
    task = asyncio.create_task(tab.wait_for_human("Sign in", timeout=30))
    try:
        await _click_node(tab, await _done_button(tab))
        assert await _until_settled(task, 5), await banner_probe.report(tab)
        await task
    finally:
        task.cancel()


@needs_display
async def test_the_wait_brings_its_tab_to_the_front(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/basic.html")
    await _focus_elsewhere(headed)
    task = asyncio.create_task(tab.wait_for_human("Sign in", timeout=30))
    try:
        await _done_button(tab)
        assert await _has_focus(tab)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _lost_focus(tab, timeout: float = 10) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if not await tab.eval("document.hasFocus()"):
            return True
        await asyncio.sleep(0.1)
    return False


@pytest.mark.skipif(sys.platform != "darwin", reason="Finder is a macOS program")
async def test_done_lands_when_another_program_is_in_front(headed, local_server):
    """Another program came to the front after Chrome (as in a long run of
    tests, or a person switching away): Chrome is not the active program."""
    tab = headed.main_tab
    await tab.get(f"{local_server}/basic.html")
    finder = await asyncio.create_subprocess_exec("open", "-a", "Finder")
    assert await asyncio.wait_for(finder.wait(), 30) == 0
    assert await _lost_focus(tab), "Finder did not take the focus from Chrome"
    task = asyncio.create_task(tab.wait_for_human("Sign in", timeout=30))
    try:
        await _click_node(tab, await _done_button(tab))
        assert await _until_settled(task, 5), await banner_probe.report(tab)
        await task
    finally:
        task.cancel()

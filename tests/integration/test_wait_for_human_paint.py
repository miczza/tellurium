"""The banner's "Done" on a page that has not painted yet (a window just
opened, a render-blocking stylesheet still loading): Chrome drops the press
of a click there, so the button comes with the page's first paint, when a
person can see it and a click on it lands."""

from __future__ import annotations

import asyncio

import pytest

from tests.integration import banner_probe
from tests.integration.test_wait_for_human import (
    _click_node,
    _closed_roots,
    _done_button,
    _until_settled,
    _walk,
)
from tests.platform_marks import needs_display
from tests.timeout_scale import scaled


@pytest.fixture
async def headed():
    from tellurium import Browser

    b = await Browser.launch(headless=False)
    yield b
    await b.close()


async def _paints(tab) -> int:
    return await tab.eval("performance.getEntriesByType('paint').length")


async def _banner_up(tab, timeout: float | None = None) -> list[dict]:
    """The banner's closed shadow root, once it is in the document."""
    timeout = scaled(10) if timeout is None else timeout
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if roots := await _closed_roots(tab):
            return roots
        await asyncio.sleep(0.05)
    raise AssertionError("no banner appeared")


@needs_display
async def test_done_comes_with_the_first_paint(headed, local_server):
    tab = headed.main_tab
    await tab.get(f"{local_server}/human_unpainted.html", wait_until="commit")
    task = asyncio.create_task(tab.wait_for_human("Sign in", timeout=scaled(30)))
    try:
        roots = await _banner_up(tab)
        assert await _paints(tab) == 0, "the stylesheet came before the banner"
        buttons = [n for r in roots for n in _walk(r) if n.get("nodeName", "").upper() == "BUTTON"]
        assert buttons == []  # nobody can see it yet, and a press there is dropped
        button = await _done_button(tab)
        assert await _paints(tab) > 0
        await _click_node(tab, button)
        assert await _until_settled(task, scaled(5)), await banner_probe.report(tab)
        await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

"""A crashed renderer fails the tab's commands instead of hanging them (M3).

``Page.crash`` does not reliably kill the renderer on recent Chrome builds
(the renderer hangs instead), so the crash is produced the way an OOM killer
would: SIGKILL on the renderer processes.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys

import pytest

from tellurium.cdp.types import TargetCrashedError

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="kills renderers with SIGKILL")


async def _kill_renderers(browser) -> None:
    info = await browser._router.root.send("SystemInfo.getProcessInfo", {}, timeout=10)
    for proc in info["processInfo"]:
        if proc["type"] == "renderer":
            try:
                os.kill(proc["id"], signal.SIGKILL)
            except ProcessLookupError:
                pass


async def _wait_until(predicate, timeout: float = 10.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


async def test_crash_fails_pending_and_future_commands(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")
    pending = asyncio.ensure_future(tab.eval("new Promise(() => {})"))
    await asyncio.sleep(0.2)

    await _kill_renderers(browser)

    with pytest.raises(TargetCrashedError):
        await asyncio.wait_for(pending, timeout=10)
    with pytest.raises(TargetCrashedError):
        await asyncio.wait_for(tab.eval("1 + 1"), timeout=10)


async def test_crashed_tab_leaves_browser_tabs(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")

    await _kill_renderers(browser)

    assert await _wait_until(lambda: tab not in browser.tabs), "crashed tab still listed"
    assert tab.closed


async def test_browser_keeps_working_after_a_crash(browser, local_server):
    await browser.main_tab.get(f"{local_server}/basic.html")
    await _kill_renderers(browser)
    await _wait_until(lambda: not browser.tabs)

    fresh = await asyncio.wait_for(browser.new_tab(f"{local_server}/basic.html"), timeout=30)
    assert await asyncio.wait_for(fresh.eval("1 + 1"), timeout=10) == 2


def test_target_crashed_error_is_a_connection_error():
    """Callers that already handle a closed session keep working."""
    assert issubclass(TargetCrashedError, ConnectionError)

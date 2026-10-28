"""browser.close() asks Chrome to close over CDP before any signal, so a cookie
written right before it is on disk at the next launch, even without Session."""

from __future__ import annotations

import asyncio
import os
import signal
import sys

import pytest

from tellurium import Browser
from tellurium.browser import process as process_module

#: SIGTERM alone loses the last cookie about one time in four (docs/gotchas.md).
ROUNDS = 20


async def test_a_cookie_written_right_before_close_survives_a_relaunch(tmp_path, local_server):
    profile = str(tmp_path / "profile")
    lost: list[str] = []
    for round_ in range(ROUNDS + 1):
        browser = await Browser.launch(headless=True, user_data_dir=profile)
        try:
            if round_:
                jar = {c.name: c.value for c in await browser.get_cookies("127.0.0.1")}
                if jar.get(f"late{round_ - 1}") != "1":
                    lost.append(f"late{round_ - 1}")
            if round_ < ROUNDS:
                tab = await browser.get(f"{local_server}/basic.html")
                await tab.eval(f"document.cookie = 'late{round_}=1; path=/; max-age=3600'")
                await asyncio.sleep(0.05)
        finally:
            await browser.close()
    assert not lost, f"lost at relaunch: {lost}"


@pytest.mark.skipif(sys.platform == "win32", reason="SIGSTOP")
async def test_a_chrome_that_ignores_browser_close_is_signalled_after_the_grace():
    browser = await Browser.launch(headless=True)
    chrome = browser._proc.process
    os.kill(chrome.pid, signal.SIGSTOP)  # deaf to Browser.close and SIGTERM alike
    loop = asyncio.get_running_loop()
    start = loop.time()
    try:
        await browser.close()
    finally:
        if chrome.poll() is None:
            chrome.kill()
            chrome.wait(5)
    elapsed = loop.time() - start
    assert chrome.returncode == -signal.SIGKILL
    # The grace, then SIGTERM's 5 s, then SIGKILL.
    assert process_module.CLOSE_GRACE <= elapsed < process_module.CLOSE_GRACE + 5 + 3


@pytest.mark.parametrize("headless", [True, False], ids=["headless", "headed"])
async def test_browser_headless_says_how_it_was_launched(headless):
    browser = await Browser.launch(headless=headless)
    try:
        assert browser.headless is headless
    finally:
        await browser.close()


@pytest.mark.parametrize("flag", ["--headless", "--headless=new"])
async def test_headless_in_args_counts_as_headless(flag):
    browser = await Browser.launch(args=[flag])
    try:
        assert browser.headless is True
    finally:
        await browser.close()


async def test_a_close_cancelled_during_browser_close_still_stops_chrome():
    browser = await Browser.launch(headless=True)
    chrome = browser._proc.process
    profile = browser._proc.temp_profile
    closing = asyncio.ensure_future(browser.close())
    for _ in range(3):
        await asyncio.sleep(0.01)
        closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    # Exit code 0 (Browser.close) when the machine is idle; under heavy load the
    # escalation may end it instead: either way it is gone.
    assert chrome.poll() is not None, "Chrome still running"
    assert not os.path.exists(profile)

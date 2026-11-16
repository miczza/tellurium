"""browser.close() asks Chrome to close over CDP before any signal, so a cookie
written right before it is on disk at the next launch, even without Session."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import warnings

import pytest

from tellurium import Browser
from tellurium.browser import process as process_module
from tests.timeout_scale import scaled

#: SIGTERM alone loses the last cookie about one time in four (docs/gotchas.md).
ROUNDS = 20
#: Chrome waits for its network service at most about 10 s while it closes,
#: then exits with 0 without the cookie store's last commit: with its services
#: frozen 12 s on Windows the cookie was lost 5/5, close taking 10.1 s (run
#: 43867327399). A runner stalled that long (8.4 s and 9.7 s seen in this test)
#: shows Chrome's limit, not close's; such a round is reported, not checked.
CHROME_GIVES_UP = 9.0


async def test_a_cookie_written_right_before_close_survives_a_relaunch(tmp_path, local_server):
    profile = str(tmp_path / "profile")
    lost: list[str] = []
    slow: dict[str, float] = {}
    loop = asyncio.get_running_loop()
    for round_ in range(ROUNDS + 1):
        browser = await Browser.launch(headless=True, user_data_dir=profile)
        try:
            if round_:
                name = f"late{round_ - 1}"
                jar = {c.name: c.value for c in await browser.get_cookies("127.0.0.1")}
                if jar.get(name) != "1" and name not in slow:
                    lost.append(name)
            if round_ < ROUNDS:
                tab = await browser.get(f"{local_server}/basic.html")
                await tab.eval(f"document.cookie = 'late{round_}=1; path=/; max-age=3600'")
                await _until_in_the_store(browser, f"late{round_}")
        finally:
            start = loop.time()
            await browser.close()
            if loop.time() - start >= CHROME_GIVES_UP:
                slow[f"late{round_}"] = loop.time() - start
    if slow:
        warnings.warn(f"closes past Chrome's own limit, not checked: {slow}", stacklevel=1)
    assert len(slow) <= ROUNDS // 2, f"too few rounds checked: {slow}"
    assert not lost, f"lost at relaunch: {lost}"


async def _until_in_the_store(browser: Browser, name: str) -> None:
    """The renderer hands ``document.cookie`` to the cookie store on its own
    channel, after the eval has answered. What close must keep is a cookie the
    store has, so the test waits for that, then closes."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + scaled(5)
    while not any(c.name == name for c in await browser.get_cookies("127.0.0.1")):
        assert loop.time() < deadline, f"{name} never reached the cookie store"
        await asyncio.sleep(0.01)


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

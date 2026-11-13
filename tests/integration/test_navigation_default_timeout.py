"""``Tab.get`` without a timeout reads the default navigation deadline at
each call: a slow machine (or the CI, ``tests.timeout_scale``) may stretch it."""

from __future__ import annotations

import asyncio

import pytest

from tellurium import NavigationTimeoutError
from tellurium.browser import navigation
from tests.process_freeze import freeze, thaw


async def test_a_navigation_without_a_timeout_takes_the_default_of_the_moment(
    browser, local_server, monkeypatch
):
    monkeypatch.setattr(navigation, "NAVIGATION_TIMEOUT", 1.0)
    with pytest.raises(NavigationTimeoutError) as caught:
        await browser.main_tab.get(f"{local_server}/slow/5000/x")
    assert caught.value.timeout == 1.0 and caught.value.phase == "commit"


async def test_an_explicit_timeout_wins_over_the_default(browser, local_server, monkeypatch):
    monkeypatch.setattr(navigation, "NAVIGATION_TIMEOUT", 0.5)
    await browser.main_tab.get(f"{local_server}/basic.html", timeout=30)
    assert browser.main_tab.url.endswith("/basic.html")


async def test_page_enable_before_a_navigation_takes_the_lifecycle_default_of_the_moment(
    browser, local_server, monkeypatch
):
    """A fresh tab enables ``Page`` first, bounded by ``LIFECYCLE_TIMEOUT`` as it
    is at the call: on a frozen Chrome the navigation gives up when that 1 s
    expires (and Chrome, thawed at 3 s, answers ``Page.stopLoading``), not at
    its own 20 s nor at the 10 s default."""
    monkeypatch.setattr(navigation, "NAVIGATION_TIMEOUT", 20.0)
    monkeypatch.setattr(navigation, "LIFECYCLE_TIMEOUT", 1.0)
    pid = browser._proc.process.pid
    loop = asyncio.get_running_loop()
    thawed = False

    def thaw_once() -> None:
        nonlocal thawed
        if not thawed:
            thawed = True
            thaw(pid)

    freeze(pid)
    thawing = loop.call_later(3.0, thaw_once)
    started = loop.time()
    try:
        with pytest.raises(NavigationTimeoutError) as caught:
            await browser.main_tab.get(f"{local_server}/basic.html")
    finally:
        thawing.cancel()
        thaw_once()
    elapsed = loop.time() - started
    assert caught.value.timeout == 20.0 and caught.value.phase == "commit"
    assert elapsed < 8.0, elapsed

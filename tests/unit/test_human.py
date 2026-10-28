"""wait_for_human with a fake tab: a busy page (CDP calls timing out) delays
the wait instead of failing it."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from tellurium.browser import human


def _tab(replies):
    """A headless tab whose Page.getFrameTree replies come from *replies*."""

    async def send(method, params=None, timeout=None):
        assert method == "Page.getFrameTree"
        reply = replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return {"frameTree": {"frame": {"id": "F", "loaderId": "L", "url": reply}}}

    browser = SimpleNamespace(headless=True)
    return SimpleNamespace(_session=SimpleNamespace(send=send, on=MagicMock()), _browser=browser)


async def test_a_busy_page_is_waited_for(monkeypatch):
    monkeypatch.setattr(human, "POLL", 0.01)
    replies = [asyncio.TimeoutError("busy"), "http://x/login", "http://x/dashboard"]
    await human.wait_for_human(_tab(replies), "Sign in", until="*/dashboard", timeout=5)
    assert replies == []


async def test_a_busy_page_still_honours_the_timeout(monkeypatch):
    monkeypatch.setattr(human, "POLL", 0.01)
    replies = [asyncio.TimeoutError("busy")] * 1000
    loop = asyncio.get_running_loop()
    start = loop.time()
    try:
        await human.wait_for_human(_tab(replies), "Sign in", until="*/dashboard", timeout=0.2)
    except TimeoutError as exc:
        assert "Sign in" in str(exc)
    else:
        raise AssertionError("no TimeoutError")
    assert loop.time() - start < 2


def _version_tab(headless: bool, product: str):
    async def send(method, params=None, timeout=None):
        assert method == "Browser.getVersion"
        return {"product": product, "userAgent": product}

    # Windows: the process object has no args to read.
    browser = SimpleNamespace(
        headless=headless,
        _proc=SimpleNamespace(process=object()),
        _router=SimpleNamespace(root=SimpleNamespace(send=send)),
    )
    return SimpleNamespace(_browser=browser)


async def test_headless_comes_from_how_the_browser_was_launched():
    # --user-agent rewrote what Chrome reports: only the launch knows.
    assert await human._headless(_version_tab(True, "Chrome/156.0.0.0"))


async def test_a_headed_browser_is_not_headless():
    assert not await human._headless(_version_tab(False, "Chrome/156.0.0.0"))

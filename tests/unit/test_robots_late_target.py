"""A hidden robots.txt target whose creation the caller gave up on is closed
when Chrome's reply lands, however late."""

from __future__ import annotations

import asyncio
import math
from types import SimpleNamespace

import pytest

from tellurium.browser import robots


class _SlowRoot:
    """A root session whose Target.createTarget reply lands when told to, later
    than any clock: a send with a finite timeout has dropped it by then (as a
    real session drops a late reply)."""

    def __init__(self) -> None:
        self.answer = asyncio.Event()
        self.closed: list[str] = []

    async def send(self, method, params=None, timeout=None):
        if method == "Target.closeTarget":
            self.closed.append(params["targetId"])
            return {}
        assert method == "Target.createTarget"
        await self.answer.wait()
        if timeout != math.inf:
            raise TimeoutError("Target.createTarget got no reply in time")
        return {"targetId": "late"}


async def test_a_hidden_target_created_after_the_caller_gave_up_is_closed(monkeypatch):
    root = _SlowRoot()
    browser = SimpleNamespace(_router=SimpleNamespace(root=root), _background=set())
    monkeypatch.setattr(robots, "_OPEN_TIMEOUT", 0.05)
    with pytest.raises(TimeoutError):
        await robots.open_frame(browser, "")
    await asyncio.sleep(0.1)
    root.answer.set()
    for _ in range(50):
        if root.closed:
            break
        await asyncio.sleep(0.01)
    assert root.closed == ["late"]


async def test_the_late_reply_is_owned_by_the_browser(monkeypatch):
    """The wait for a reply with no clock is a task of the browser, which
    cancels it when it closes."""
    root = _SlowRoot()
    browser = SimpleNamespace(_router=SimpleNamespace(root=root), _background=set())
    monkeypatch.setattr(robots, "_OPEN_TIMEOUT", 0.05)
    with pytest.raises(TimeoutError):
        await robots.open_frame(browser, "")
    (create,) = browser._background
    assert not create.done()
    create.cancel()
    await asyncio.wait({create})
    await asyncio.sleep(0)  # the done callbacks
    assert browser._background == set()
    assert root.closed == []

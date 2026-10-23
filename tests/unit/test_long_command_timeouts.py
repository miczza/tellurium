"""Long page operations are bounded by their own deadline, not by the 30 s
session default (R1 integration of parts A and B)."""

import math

import pytest

from tellurium.browser.navigation import navigate
from tellurium.browser.tab import Tab


class _RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float | None]] = []

    def on(self, event, handler) -> None:
        pass

    def off(self, event, handler) -> None:
        pass

    def remove_listener(self, event, handler) -> None:
        pass

    async def send(self, method, params=None, timeout=None):
        self.calls.append((method, timeout))
        if method == "Page.navigate":
            return {"frameId": "F", "loaderId": "L"}
        if method == "Runtime.evaluate":
            return {"result": {"type": "number", "value": 2}}
        return {}


@pytest.mark.asyncio
async def test_page_navigate_is_bounded_by_the_navigation_deadline():
    session = _RecordingSession()
    await navigate(session, "http://example.test/", wait_until="commit", timeout=60)
    timeouts = [t for m, t in session.calls if m == "Page.navigate"]
    assert timeouts == [math.inf]


@pytest.mark.asyncio
async def test_eval_passes_its_timeout_to_the_session():
    session = _RecordingSession()
    tab = Tab.__new__(Tab)
    tab._session = session
    assert await tab.eval("1 + 1", timeout=120) == 2
    assert await tab.eval("1 + 1") == 2
    assert [t for m, t in session.calls if m == "Runtime.evaluate"] == [120, None]

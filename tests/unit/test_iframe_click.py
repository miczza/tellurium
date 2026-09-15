"""Tests for Tab.click_in_iframe — viewport-space coordinate translation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from tellurium.browser.tab import Tab


def _fake_tab():
    tab = Tab.__new__(Tab)
    tab._session = MagicMock()
    tab._session.send = AsyncMock()
    tab._hsim_worlds = {"ROOT": 55}
    tab._frame_id = "ROOT"
    tab._mouse_pos = (0, 0)
    return tab


def test_click_in_iframe_translates_to_viewport_coords():
    """Iframe at viewport (400, 300); local click (20, 20) → viewport (420, 320)."""
    tab = _fake_tab()
    # First call: Runtime.evaluate returns iframe rect {x:400, y:300}
    # Subsequent calls: mouseMoved + mousePressed + mouseReleased (via mouse_click)
    tab._session.send.side_effect = [
        {"result": {"value": {"x": 400.0, "y": 300.0}}},  # iframe rect
        None,  # mousePressed
        None,  # mouseReleased
    ]

    async def run():
        await tab.click_in_iframe("#cf-turnstile iframe", 20.0, 20.0, human=False)

    asyncio.run(run())

    # Inspect the mousePressed call
    press_calls = [
        c
        for c in tab._session.send.call_args_list
        if c[0][0] == "Input.dispatchMouseEvent" and c[0][1].get("type") == "mousePressed"
    ]
    assert len(press_calls) == 1
    params = press_calls[0][0][1]
    assert params["x"] == 420.0
    assert params["y"] == 320.0


def test_click_in_iframe_missing_iframe_raises():
    """Selector that matches nothing → ValueError with the selector in the message."""
    tab = _fake_tab()
    tab._session.send.side_effect = [
        {"result": {"value": None}},  # querySelector returned null
    ]

    async def run():
        await tab.click_in_iframe("#missing", 5, 5, human=False)

    with pytest.raises(ValueError, match="#missing"):
        asyncio.run(run())

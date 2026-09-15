"""P0.4 — screenX/screenY parity for CDP-dispatched mouse events.

Design doc 04 §P0.4 assumed Chrome reports ``screenX === clientX`` for
``Input.dispatchMouseEvent``. Measured on Chrome 153 stock that assumption no
longer holds: the browser itself adds the window origin and the chrome-UI
height. These tests pin the *observable* contract (parity with a real user's
event) rather than any particular implementation of it, so they keep working
whichever side computes the offset.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

PAGE = (
    "data:text/html,<html><body style='margin:0'>"
    "<div style='width:900px;height:900px'></div><script>"
    "window.__ev=null;document.addEventListener('mousedown',e=>{window.__ev="
    "{cx:e.clientX,cy:e.clientY,sx:e.screenX,sy:e.screenY,t:e.isTrusted};});"
    "</script></body></html>"
)

HEADED = bool(os.environ.get("DISPLAY"))


async def _click_and_read(tab, x=123, y=234) -> dict:
    await tab.eval("window.__ev = null")
    await tab.mouse_click(x, y)
    for _ in range(20):
        raw = await tab.eval("JSON.stringify(window.__ev)")
        if raw and raw != "null":
            return json.loads(raw)
        await asyncio.sleep(0.05)
    raise AssertionError("mousedown never observed")


@pytest.mark.asyncio
@pytest.mark.parametrize("stealth", [False, True])
async def test_screen_coords_are_offset_from_client_coords(stealth):
    """screenX/screenY must never be *below* clientX/clientY, and must track
    the window origin — the signal Turnstile keys on is screenX == clientX."""
    from tellurium import Browser

    browser = await Browser.launch(headless=not HEADED, stealth=stealth)
    try:
        tab = browser.main_tab
        await tab.get(PAGE)
        ev = await _click_and_read(tab)

        assert ev["t"] is True
        dx = ev["sx"] - ev["cx"]
        dy = ev["sy"] - ev["cy"]
        assert dx >= 0 and dy >= 0, f"negative screen offset: {ev}"
        # Chrome UI (tab strip + omnibox) is always above the viewport.
        assert dy > 0, f"screenY == clientY (no chrome-UI offset): {ev}"

        win_x = await tab.eval("window.screenX")
        win_y = await tab.eval("window.screenY")
        chrome_ui = await tab.eval("window.outerHeight - window.innerHeight")
        # Headed windows add a frame border on top of window.screenX.
        assert dx >= win_x, f"dx={dx} below window.screenX={win_x}"
        assert dy >= win_y, f"dy={dy} below window.screenY={win_y}"
        if chrome_ui and chrome_ui > 0:
            # dy = window origin + chrome UI (outerHeight-innerHeight is an
            # estimate: on headed Linux it also covers the bottom frame).
            assert dy <= win_y + chrome_ui + 2
    finally:
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.skipif(not HEADED, reason="needs a real X display (DISPLAY=:0)")
async def test_headed_screen_offset_is_strictly_positive():
    """Headed stock Chrome: a real user's window is never at screen (0,0)
    with no frame, so both components must be > 0."""
    from tellurium import Browser

    browser = await Browser.launch(headless=False, stealth=True)
    try:
        tab = browser.main_tab
        await tab.get(PAGE)
        ev = await _click_and_read(tab)
        assert ev["sx"] - ev["cx"] > 0, f"headed screenX == clientX: {ev}"
        assert ev["sy"] - ev["cy"] > 0, f"headed screenY == clientY: {ev}"
    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_window_offset_matches_measured_event_offset():
    """Tab.window_offset() must agree with what the browser actually reports."""
    from tellurium import Browser

    browser = await Browser.launch(headless=not HEADED, stealth=True)
    try:
        tab = browser.main_tab
        await tab.get(PAGE)
        ev = await _click_and_read(tab)
        dx, dy = await tab.window_offset()
        assert abs((ev["sx"] - ev["cx"]) - dx) <= 12, (
            f"window_offset dx={dx} vs measured {ev['sx'] - ev['cx']}"
        )
        assert abs((ev["sy"] - ev["cy"]) - dy) <= 12, (
            f"window_offset dy={dy} vs measured {ev['sy'] - ev['cy']}"
        )
        # Cached: a second call must not re-query the browser.
        assert await tab.window_offset() == (dx, dy)
    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_parity_nudges_window_pinned_at_screen_origin():
    """A window at (0,0) makes screenX == clientX exactly; stealth must move
    it so the coordinates look like a real user's."""
    from tellurium import Browser

    browser = await Browser.launch(
        headless=True, stealth=True, args=["--window-position=0,0"],
    )
    try:
        tab = browser.main_tab
        await tab.get(PAGE)
        ev = await _click_and_read(tab)
        assert ev["sx"] - ev["cx"] > 0, f"window not nudged off origin: {ev}"
    finally:
        await browser.close()

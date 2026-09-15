"""P0.4 — window-offset resolution and screenX/screenY parity guard."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tellurium.browser.tab import Tab


def _make_tab(*, caps=frozenset(), stealth=True, bounds=None, js=None):
    """Tab with a mocked router root + a stubbed isolated-world eval."""
    root = MagicMock()
    sent: list[tuple[str, dict]] = []

    async def _root_send(method, params=None, timeout=None):
        sent.append((method, params or {}))
        if method == "Browser.getWindowForTarget":
            return {"windowId": 7, "bounds": dict(bounds or {})}
        if method == "Browser.getWindowBounds":
            return {"bounds": dict(bounds or {})}
        return {}

    root.send = AsyncMock(side_effect=_root_send)

    browser = MagicMock()
    browser._router.root = root
    browser._stealth_engine = MagicMock() if stealth else None
    browser._engine.capabilities.return_value = set(caps)

    session = MagicMock()
    session.send = AsyncMock(return_value={})
    session.on = MagicMock()

    tab = Tab(session, browser, "T1")
    tab._eval_isolated = AsyncMock(return_value=js)
    tab._sent_root = sent
    return tab


@pytest.mark.asyncio
async def test_window_offset_uses_bounds_and_chrome_ui():
    tab = _make_tab(
        bounds={"left": 150, "top": 60, "width": 900, "height": 700},
        js=[150, 60, 700, 613],  # screenX, screenY, outerHeight, innerHeight
    )
    assert await tab.window_offset() == (150.0, 60.0 + 87.0)


@pytest.mark.asyncio
async def test_window_offset_is_cached():
    tab = _make_tab(bounds={"left": 10, "top": 10, "height": 580}, js=[10, 10, 580, 493])
    first = await tab.window_offset()
    calls = len(tab._sent_root)
    assert await tab.window_offset() == first
    assert len(tab._sent_root) == calls, "window_offset re-queried the browser"


@pytest.mark.asyncio
async def test_window_offset_falls_back_to_window_bounds_height():
    """window.outerHeight reads 0 on a freshly mapped headed window."""
    tab = _make_tab(
        bounds={"left": 0, "top": 0, "width": 1042, "height": 1256},
        js=[0, 0, 0, 1150],
    )
    assert await tab.window_offset() == (0.0, 106.0)


@pytest.mark.asyncio
async def test_window_offset_falls_back_to_js_when_cdp_unavailable():
    """Browser.getWindowBounds is not implemented on every backend."""
    tab = _make_tab(js=[33, 44, 700, 600])
    tab._browser._router.root.send = AsyncMock(side_effect=RuntimeError("not supported"))
    assert await tab.window_offset() == (33.0, 44.0 + 100.0)


@pytest.mark.asyncio
async def test_parity_noop_without_stealth():
    tab = _make_tab(stealth=False, bounds={"left": 0, "top": 0})
    await tab._ensure_screen_parity()
    assert tab._sent_root == []


@pytest.mark.asyncio
async def test_parity_noop_on_patched_backend():
    """native_cdp_fix means input_handler.cc already fixes screenX/screenY."""
    tab = _make_tab(caps={"native_cdp_fix"}, bounds={"left": 0, "top": 0})
    await tab._ensure_screen_parity()
    assert tab._sent_root == []


@pytest.mark.asyncio
async def test_parity_leaves_a_plausible_window_alone():
    tab = _make_tab(bounds={"left": 150, "top": 60, "height": 700}, js=[150, 60, 700, 613])
    await tab._ensure_screen_parity()
    assert not any(m == "Browser.setWindowBounds" for m, _ in tab._sent_root)


@pytest.mark.asyncio
async def test_parity_nudges_window_at_screen_origin():
    """Window at (0,0) with no chrome UI => screenX == clientX exactly."""
    tab = _make_tab(bounds={"left": 0, "top": 0, "height": 600}, js=[0, 0, 600, 600])
    await tab._ensure_screen_parity()
    moves = [p for m, p in tab._sent_root if m == "Browser.setWindowBounds"]
    assert len(moves) == 1
    assert moves[0]["windowId"] == 7
    assert moves[0]["bounds"]["left"] > 0
    assert moves[0]["bounds"]["top"] > 0


@pytest.mark.asyncio
async def test_parity_runs_only_once_per_tab():
    tab = _make_tab(bounds={"left": 0, "top": 0, "height": 600}, js=[0, 0, 600, 600])
    await tab._ensure_screen_parity()
    calls = len(tab._sent_root)
    await tab._ensure_screen_parity()
    assert len(tab._sent_root) == calls


@pytest.mark.asyncio
async def test_mouse_dispatch_triggers_parity_once():
    tab = _make_tab(bounds={"left": 150, "top": 60, "height": 700}, js=[150, 60, 700, 613])
    await tab.mouse_move(10, 10)
    await tab.mouse_click(10, 10)
    assert tab._screen_parity_done
    mouse = [c.args[0] for c in tab._session.send.await_args_list]
    assert mouse.count("Input.dispatchMouseEvent") == 3  # move + press + release


@pytest.mark.asyncio
async def test_parity_failure_never_blocks_input():
    tab = _make_tab(bounds={"left": 0, "top": 0, "height": 600}, js=[0, 0, 600, 600])
    tab._eval_isolated = AsyncMock(side_effect=RuntimeError("boom"))
    await tab.mouse_click(10, 10)  # must not raise
    mouse = [c.args[0] for c in tab._session.send.await_args_list]
    assert mouse.count("Input.dispatchMouseEvent") == 2

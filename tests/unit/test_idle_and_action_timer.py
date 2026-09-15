"""Design doc 05 wiring: IdleSimulator (stealth_idle) and ActionTimer (human).

Both used to be dead code; these tests pin the wiring so they stay reachable.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tellurium.browser.tab import Tab
from tellurium.stealth.human import ACTION_TRANSITION_DELAYS, ActionTimer
from tellurium.stealth.idle import IdleSimulator


def _fake_tab(**kwargs) -> Tab:
    browser = MagicMock()
    browser._stealth_engine = None  # skip the P0.4 parity probe
    session = MagicMock()
    session.send = AsyncMock(return_value={})
    session.on = MagicMock()
    return Tab(session, browser, "T1", **kwargs)


# ---------------------------------------------------------------------------
# IdleSimulator
# ---------------------------------------------------------------------------


def test_tab_has_no_idle_simulator_by_default():
    assert _fake_tab()._idle_simulator is None


def test_stealth_idle_creates_simulator():
    tab = _fake_tab(stealth_idle=True)
    assert isinstance(tab._idle_simulator, IdleSimulator)


@pytest.mark.asyncio
async def test_wait_without_idle_just_sleeps():
    tab = _fake_tab()
    with patch("asyncio.sleep", new=AsyncMock()) as sleeper:
        await tab.wait(1.25)
    sleeper.assert_awaited_once_with(1.25)


@pytest.mark.asyncio
async def test_wait_with_idle_emits_mouse_moves():
    tab = _fake_tab(stealth_idle=True)
    tab.mouse_move = AsyncMock()

    # Force every iteration to pick a micro-move and to sleep ~instantly.
    with (
        patch("tellurium.stealth.idle.random.choices", return_value=["micro_move"]),
        patch("tellurium.stealth.idle.random.uniform", return_value=0.001),
    ):
        await tab.wait(0.05)

    assert tab.mouse_move.await_count >= 1
    for call in tab.mouse_move.await_args_list:
        x, y = call.args
        assert x > 0 and y > 0, "idle must not move the cursor off-viewport"


@pytest.mark.asyncio
async def test_idle_never_overshoots_requested_duration():
    tab = _fake_tab(stealth_idle=True)
    tab.mouse_move = AsyncMock()
    loop = asyncio.get_running_loop()
    start = loop.time()
    await tab.wait(0.2)
    assert loop.time() - start < 0.6, "idle loop overshot tab.wait()"


@pytest.mark.asyncio
async def test_idle_seeds_from_current_mouse_position():
    tab = _fake_tab(stealth_idle=True)
    tab._mouse_pos = (640.0, 480.0)
    tab.mouse_move = AsyncMock()
    with (
        patch("tellurium.stealth.idle.random.choices", return_value=["micro_move"]),
        patch("tellurium.stealth.idle.random.uniform", return_value=0.001),
        patch("tellurium.stealth.idle.random.gauss", return_value=0.0),
    ):
        await tab.wait(0.02)
    x, y = tab.mouse_move.await_args_list[0].args
    assert (x, y) == (640.0, 480.0)


# ---------------------------------------------------------------------------
# ActionTimer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_timer_first_action_has_no_delay():
    timer = ActionTimer()
    with patch("tellurium.stealth.human.asyncio.sleep", new=AsyncMock()) as s:
        await timer.delay_between("click")
    s.assert_not_awaited()


@pytest.mark.asyncio
async def test_action_timer_uses_transition_table():
    timer = ActionTimer()
    timer.mark("scroll")
    with patch("tellurium.stealth.human.asyncio.sleep", new=AsyncMock()) as s:
        await timer.delay_between("click")
    low, high = ACTION_TRANSITION_DELAYS[("scroll", "click")]
    delay_ms = s.await_args.args[0] * 1000
    assert low <= delay_ms <= high


@pytest.mark.asyncio
async def test_action_timer_lognormal_fallback_for_unknown_pair():
    """click -> click is not in the table: fall back to a log-normal delay."""
    timer = ActionTimer()
    timer.mark("click")
    samples = []
    for _ in range(200):
        with patch("tellurium.stealth.human.asyncio.sleep", new=AsyncMock()) as s:
            await timer.delay_between("click")
        samples.append(s.await_args.args[0] * 1000)
    mean = sum(samples) / len(samples)
    assert all(0 < d <= 2000 for d in samples)
    assert 200 < mean < 450, f"log-normal mean out of range: {mean}"


@pytest.mark.asyncio
async def test_mouse_click_human_invokes_action_timer():
    tab = _fake_tab()
    tab.mouse_move = AsyncMock()
    with patch.object(ActionTimer, "delay_between", new=AsyncMock()) as spy:
        await tab.mouse_click(10, 10, human=True)
    spy.assert_awaited_once_with("click")


@pytest.mark.asyncio
async def test_keyboard_type_human_invokes_action_timer():
    tab = _fake_tab()
    with patch.object(ActionTimer, "delay_between", new=AsyncMock()) as spy:
        await tab.keyboard_type("hi", human=True)
    spy.assert_awaited_once_with("type")


@pytest.mark.asyncio
async def test_scroll_human_invokes_action_timer():
    tab = _fake_tab()
    with patch.object(ActionTimer, "delay_between", new=AsyncMock()) as spy:
        await tab.scroll(delta_y=300, human=True)
    spy.assert_awaited_once_with("scroll")


@pytest.mark.asyncio
async def test_non_human_actions_do_not_delay():
    tab = _fake_tab()
    with patch.object(ActionTimer, "delay_between", new=AsyncMock()) as spy:
        await tab.mouse_click(10, 10)
        await tab.keyboard_type("hi")
        await tab.scroll(delta_y=300)
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_action_timer_is_shared_across_consecutive_actions():
    """Two human actions on the same tab share one timer instance."""
    tab = _fake_tab()
    tab.mouse_move = AsyncMock()
    with patch("tellurium.stealth.human.asyncio.sleep", new=AsyncMock()):
        await tab.mouse_click(10, 10, human=True)
        first = tab._action_timer
        await tab.keyboard_type("a", human=True)
    assert tab._action_timer is first
    assert first._last_action_type == "type"

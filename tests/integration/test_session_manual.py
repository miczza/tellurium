"""Session.start(on_login_failure="manual") with a real Chrome: without a
display the start fails at once with an error naming it (not a launch error
with Wayland's log), and a validator that hangs hands over to the person."""

from __future__ import annotations

import asyncio

import pytest

import tellurium
from tellurium import Session
from tellurium.session import SessionLoginFailedError, manual_login
from tests.integration.test_wait_for_human import _click_node, _done_button
from tests.platform_marks import LINUX, needs_display


@pytest.fixture
def launched(monkeypatch):
    """(kwargs, browser) of each Browser.launch, as they come."""
    seen: list = []
    real_launch = tellurium.Browser.launch

    async def spying_launch(**kwargs):
        browser = await real_launch(**kwargs)
        seen.append((kwargs, browser))
        return browser

    monkeypatch.setattr(tellurium.Browser, "launch", spying_launch)
    return seen


def _session(path, validator):
    session = Session("s", path=path)
    session.validate(validator)
    return session


async def _signed_in(tab):
    return "auth=1" in await tab.eval("document.cookie")


@pytest.mark.skipif(not LINUX, reason="DISPLAY is how Linux finds one")
async def test_without_a_display_the_error_names_it_at_once(tmp_path, launched, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    session = _session(str(tmp_path / "s"), _signed_in)
    loop = asyncio.get_running_loop()
    began = loop.time()
    with pytest.raises(SessionLoginFailedError, match="display"):
        async with session.start(headless=True, on_login_failure="manual", manual_timeout=60):
            pass
    assert loop.time() - began < 5
    assert len(launched) == 1  # the headless one only, closed
    assert all(b._proc.process.poll() is not None for _, b in launched)


@needs_display
async def test_a_hung_validator_hands_over_to_a_person(
    tmp_path, local_server, launched, monkeypatch
):
    monkeypatch.setattr(manual_login, "VALIDATOR_TIMEOUT", 1.0)
    calls = []

    async def hangs_first(tab):
        calls.append(1)
        if len(calls) == 1:
            await asyncio.Event().wait()
        return "auth=1" in await tab.eval("document.cookie")

    session = _session(str(tmp_path / "s"), hangs_first)

    async def person():
        _, browser = await _launched(launched, 2)
        tab = browser.main_tab
        await tab.get(f"{local_server}/basic.html")
        await tab.eval("document.cookie = 'auth=1; path=/; max-age=3600'")
        await _click_node(tab, await _done_button(tab))

    helper = asyncio.create_task(person())
    try:
        async with session.start(headless=True, on_login_failure="manual", manual_timeout=60):
            await asyncio.wait_for(helper, 30)
    finally:
        helper.cancel()
    assert launched[1][0]["headless"] is False
    assert len(calls) == 2


async def _launched(launched, n, timeout=30.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while len(launched) < n:
        assert loop.time() < deadline, f"no launch #{n}"
        await asyncio.sleep(0.05)
    return launched[n - 1]

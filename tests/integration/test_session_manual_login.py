"""Session.start(on_login_failure="manual"): when the session is not signed in,
Chrome comes back with a window (if it was headless) and a person signs in;
the start goes on once the validators pass, inside the same start and lock."""

from __future__ import annotations

import asyncio

import pytest

import tellurium
from tellurium import Session
from tellurium.session import SessionBusyError, SessionLoginFailedError
from tests.integration.test_wait_for_human import _click_node, _done_button
from tests.platform_marks import needs_display
from tests.side_task import side_task
from tests.timeout_scale import scaled

pytestmark = needs_display


#: A Done that is lost fails the test in a minute, not in ten.
_MINUTE = 60.0


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


async def _nth(launched, n, timeout=None):
    timeout = scaled(30.0) if timeout is None else timeout
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while len(launched) < n:
        assert loop.time() < deadline, f"no launch #{n}"
        await asyncio.sleep(0.05)
    return launched[n - 1]


def _session(path, local_server):
    session = Session("s", path=path)

    @session.validate
    async def signed_in(tab):
        return "auth=1" in await tab.eval("document.cookie")

    return session


async def _sign_in(browser, local_server):
    """What the person does: sign in on the page."""
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")
    await tab.eval("document.cookie = 'auth=1; path=/; max-age=3600'")


async def test_a_headless_start_reopens_headed_and_waits_for_the_validators(
    tmp_path, local_server, launched
):
    path = str(tmp_path / "s")
    session = _session(path, local_server)

    async def person():
        _, browser = await _nth(launched, 2)
        await _sign_in(browser, local_server)
        await _click_node(browser.main_tab, await _done_button(browser.main_tab))

    async with side_task(person()) as helper:
        async with session.start(
            headless=True, on_login_failure="manual", manual_timeout=scaled(_MINUTE)
        ) as browser:
            await helper
            assert [kw.get("headless") for kw, _ in launched] == [True, False]
            assert browser is launched[1][1]
            assert "auth=1" in await browser.main_tab.eval("document.cookie")
            # Still the same start and the same lock.
            with pytest.raises(SessionBusyError):
                async with Session("s", path=path).start(headless=True):
                    pass
    assert launched[0][1]._proc.process.poll() is not None  # the headless Chrome was closed


async def test_done_before_signing_in_shows_the_banner_again(tmp_path, local_server, launched):
    session = _session(str(tmp_path / "s"), local_server)

    async def person():
        _, browser = await _nth(launched, 1)
        tab = browser.main_tab
        await tab.get(f"{local_server}/basic.html")
        await _click_node(tab, await _done_button(tab))  # not signed in yet
        await asyncio.sleep(1.0)
        await _sign_in(browser, local_server)
        await _click_node(browser.main_tab, await _done_button(browser.main_tab))

    async with side_task(person()) as helper:
        async with session.start(
            headless=False, on_login_failure="manual", manual_timeout=scaled(_MINUTE)
        ) as browser:
            await helper
            assert len(launched) == 1  # headed already: no second Chrome
            assert "auth=1" in await browser.main_tab.eval("document.cookie")


async def test_a_login_callback_that_fails_hands_over_to_a_person(tmp_path, local_server, launched):
    session = _session(str(tmp_path / "s"), local_server)

    @session.login
    async def broken(tab, metadata):
        raise RuntimeError("the form changed")

    async def person():
        _, browser = await _nth(launched, 1)
        await _sign_in(browser, local_server)
        await _click_node(browser.main_tab, await _done_button(browser.main_tab))

    async with side_task(person()) as helper:
        async with session.start(
            headless=False, on_login_failure="manual", manual_timeout=scaled(_MINUTE)
        ):
            await helper


async def test_nobody_signing_in_fails_the_start(tmp_path, local_server, launched):
    session = _session(str(tmp_path / "s"), local_server)
    with pytest.raises(SessionLoginFailedError, match="within"):
        async with session.start(headless=True, on_login_failure="manual", manual_timeout=1.5):
            pass
    assert all(b._proc.process.poll() is not None for _, b in launched)


async def test_an_unknown_policy_is_refused(tmp_path):
    with pytest.raises(ValueError, match="on_login_failure"):
        async with Session("s", path=str(tmp_path / "s")).start(on_login_failure="ask"):
            pass

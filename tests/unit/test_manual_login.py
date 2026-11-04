"""Session.start(on_login_failure="manual") without Chrome: no display is a
clear error, validators that hang are bounded, the time a person gets is the
start's *manual_timeout*."""

from __future__ import annotations

import asyncio
import sys

import pytest

import tellurium
from tellurium import Session
from tellurium.browser import human
from tellurium.session import SessionLoginFailedError, manual_login


class _FakeBrowser:
    def __init__(self, headless):
        self.headless = headless
        self.main_tab = object()

    async def get_cookies(self, domain=None):
        return []

    async def set_cookies(self, cookies):
        pass

    async def close(self):
        pass


@pytest.fixture
def launched(monkeypatch):
    seen: list[dict] = []

    async def launch(**kwargs):
        seen.append(kwargs)
        return _FakeBrowser(kwargs.get("headless"))

    monkeypatch.setattr(tellurium.Browser, "launch", launch)
    return seen


@pytest.fixture
def done(monkeypatch):
    """wait_for_human: "Done" at once, or never (until its timeout) once cleared."""
    clicks = asyncio.Event()
    clicks.set()

    async def wait_for_human(tab, reason, timeout=None, **kwargs):
        await asyncio.wait_for(clicks.wait(), timeout)

    monkeypatch.setattr(human, "wait_for_human", wait_for_human)
    return clicks


def _session(path, *answers):
    """A session whose validator gives *answers* one call after the other
    (``"hang"``: never returns)."""
    session = Session("s", path=path)
    calls = iter(answers)

    @session.validate
    async def check(tab):
        answer = next(calls)
        if answer == "hang":
            await asyncio.Event().wait()
        return answer

    return session


@pytest.fixture
def no_display(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="a Linux without X11 or Wayland: on Windows there is always a display, and "
    "faking sys.platform sends the session lock to fcntl",
)
async def test_without_a_display_the_error_says_so(tmp_path, launched, done, no_display):
    session = _session(str(tmp_path), False)
    with pytest.raises(SessionLoginFailedError, match="display"):
        async with session.start(headless=True, on_login_failure="manual"):
            pass
    assert len(launched) == 1  # no headed Chrome tried


def test_a_display_is_any_of_x11_or_wayland(monkeypatch, no_display):
    assert not manual_login.has_display()
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert manual_login.has_display()
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("WAYLAND_DISPLAY")
    assert manual_login.has_display()


async def test_a_hung_validator_hands_over_to_a_person(tmp_path, launched, done, monkeypatch):
    monkeypatch.setattr(manual_login, "VALIDATOR_TIMEOUT", 0.05)
    monkeypatch.setenv("DISPLAY", ":99")
    session = _session(str(tmp_path), "hang", True)
    async with session.start(headless=True, on_login_failure="manual") as browser:
        assert browser.headless is False


async def test_a_validator_hung_after_done_shows_the_banner_again(
    tmp_path, launched, done, monkeypatch
):
    monkeypatch.setattr(manual_login, "VALIDATOR_TIMEOUT", 0.05)
    session = _session(str(tmp_path), False, "hang", True)
    async with session.start(headless=False, on_login_failure="manual"):
        pass


async def test_the_time_a_person_gets_is_the_start_s(tmp_path, launched, done):
    done.clear()  # nobody clicks Done
    session = _session(str(tmp_path), False)
    loop = asyncio.get_running_loop()
    began = loop.time()
    with pytest.raises(SessionLoginFailedError, match="0.2 s"):
        async with session.start(on_login_failure="manual", manual_timeout=0.2):
            pass
    assert loop.time() - began < 2


async def test_validators_hung_past_the_deadline_fail_the_start(tmp_path, launched, done):
    session = _session(str(tmp_path), False, "hang")
    with pytest.raises(SessionLoginFailedError, match="within"):
        async with session.start(on_login_failure="manual", manual_timeout=0.2):
            pass


async def test_manual_timeout_must_be_positive(tmp_path):
    with pytest.raises(ValueError, match="manual_timeout"):
        async with Session("s", path=str(tmp_path)).start(manual_timeout=0):
            pass

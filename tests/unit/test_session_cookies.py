"""Cookies with no expiry: Chrome drops them on restart, the session keeps them
in cookies.json, saved before Chrome closes and put back before the validators."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

import tellurium
from tellurium import Cookie, Session
from tellurium.session import session_cookies

_SSO = Cookie(name="sso", value="1", domain="127.0.0.1", http_only=True)
_KEPT = Cookie(name="kept", value="2", domain="127.0.0.1", expires=4102444800.0)


def test_round_trip_keeps_only_cookies_with_no_expiry(tmp_path):
    session_cookies.save(str(tmp_path), [_SSO, _KEPT])
    assert session_cookies.load(str(tmp_path)) == [_SSO]


def test_file_is_private(tmp_path):
    session_cookies.save(str(tmp_path), [_SSO])
    path = tmp_path / session_cookies.COOKIES_FILE
    assert json.loads(path.read_text())["cookies"][0]["name"] == "sso"
    if sys.platform != "win32":
        assert path.stat().st_mode & 0o777 == 0o600


def test_missing_file_is_no_cookies(tmp_path):
    assert session_cookies.load(str(tmp_path)) == []


def test_corrupt_file_warns_and_is_ignored(tmp_path):
    (tmp_path / session_cookies.COOKIES_FILE).write_text("{nope")
    with pytest.warns(UserWarning, match="cookies.json"):
        assert session_cookies.load(str(tmp_path)) == []


class _FakeBrowser:
    def __init__(self, jar=(), fail_read=False, hang_read=False):
        self.jar = list(jar)
        self.fail_read = fail_read
        self.hang_read = hang_read
        self.events: list[str] = []
        self.main_tab = object()

    async def get_cookies(self, domain=None):
        self.events.append("get_cookies")
        if self.hang_read:
            await asyncio.Event().wait()
        if self.fail_read:
            raise ConnectionError("chrome is gone")
        return list(self.jar)

    async def set_cookies(self, cookies):
        self.events.append("set_cookies")
        self.jar.extend(cookies)

    async def close(self):
        self.events.append("close")


@pytest.fixture
def fake_launch(monkeypatch):
    browsers: list[_FakeBrowser] = []
    make = {"factory": _FakeBrowser}

    async def launch(**kwargs):
        browser = make["factory"]()
        browsers.append(browser)
        return browser

    monkeypatch.setattr(tellurium.Browser, "launch", launch)
    return browsers, make


async def test_cookies_are_saved_before_chrome_closes(tmp_path, fake_launch):
    browsers, _ = fake_launch
    session = Session("s", path=str(tmp_path))
    async with session.start() as browser:
        browser.jar = [_SSO, _KEPT]
    assert browsers[0].events[-2:] == ["get_cookies", "close"]
    assert session_cookies.load(str(tmp_path)) == [_SSO]


async def test_cookies_are_saved_when_the_body_raises(tmp_path, fake_launch):
    session = Session("s", path=str(tmp_path))
    with pytest.raises(KeyError):
        async with session.start() as browser:
            browser.jar = [_SSO]
            raise KeyError("boom")
    assert session_cookies.load(str(tmp_path)) == [_SSO]


async def test_saved_cookies_go_back_before_the_validators(tmp_path, fake_launch):
    browsers, _ = fake_launch
    session_cookies.save(str(tmp_path), [_SSO])
    session = Session("s", path=str(tmp_path))
    seen = []

    @session.validate
    async def check(tab):
        seen.append(list(browsers[-1].jar))
        return True

    async with session.start():
        pass
    assert seen == [[_SSO]]
    assert browsers[0].events[0] == "set_cookies"


async def test_a_failed_read_keeps_the_previous_file(tmp_path, fake_launch):
    browsers, make = fake_launch
    session_cookies.save(str(tmp_path), [_SSO])
    make["factory"] = lambda: _FakeBrowser(fail_read=True)
    async with Session("s", path=str(tmp_path)).start():
        pass
    assert browsers[0].events[-1] == "close"
    assert session_cookies.load(str(tmp_path)) == [_SSO]


async def test_a_hung_read_is_bounded_and_chrome_still_closes(tmp_path, fake_launch, monkeypatch):
    browsers, make = fake_launch
    monkeypatch.setattr(session_cookies, "TIMEOUT", 0.05)
    make["factory"] = lambda: _FakeBrowser(hang_read=True)
    async with Session("s", path=str(tmp_path)).start():
        pass
    assert browsers[0].events[-1] == "close"


async def test_save_writes_the_cookies_known_to_the_session(tmp_path, fake_launch):
    session = Session("s", path=str(tmp_path))
    session.save()
    assert not (tmp_path / session_cookies.COOKIES_FILE).exists()  # nothing known yet
    async with session.start() as browser:
        browser.jar = [_SSO]
    (tmp_path / session_cookies.COOKIES_FILE).unlink()
    session.save()
    assert session_cookies.load(str(tmp_path)) == [_SSO]

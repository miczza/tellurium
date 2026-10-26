"""The session keeps its cookie jar in cookies.json: Chrome drops the cookies
with no expiry on restart, and can lose the last one written before it closed.
Saved before Chrome closes; those Chrome lacks go back before the validators."""

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
_GONE = Cookie(name="gone", value="3", domain="127.0.0.1", expires=1000.0)


def test_round_trip_keeps_the_cookies_not_expired(tmp_path):
    session_cookies.save(str(tmp_path), [_SSO, _KEPT, _GONE])
    assert session_cookies.load(str(tmp_path)) == [_SSO, _KEPT]


def test_cookies_that_expire_after_the_save_are_not_loaded(tmp_path, monkeypatch):
    soon = Cookie(name="soon", value="1", domain="127.0.0.1", expires=2000.0)
    monkeypatch.setattr(session_cookies.time, "time", lambda: 1500.0)
    session_cookies.save(str(tmp_path), [soon])
    monkeypatch.setattr(session_cookies.time, "time", lambda: 2500.0)
    assert session_cookies.load(str(tmp_path)) == []


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
    assert session_cookies.load(str(tmp_path)) == [_SSO, _KEPT]


async def test_cookies_are_saved_when_the_body_raises(tmp_path, fake_launch):
    session = Session("s", path=str(tmp_path))
    with pytest.raises(KeyError):
        async with session.start() as browser:
            browser.jar = [_SSO]
            raise KeyError("boom")
    assert session_cookies.load(str(tmp_path)) == [_SSO]


async def test_saved_cookies_go_back_before_the_validators(tmp_path, fake_launch):
    browsers, _ = fake_launch
    session_cookies.save(str(tmp_path), [_SSO, _KEPT])
    session = Session("s", path=str(tmp_path))
    seen = []

    @session.validate
    async def check(tab):
        seen.append(list(browsers[-1].jar))
        return True

    async with session.start():
        pass
    assert seen == [[_SSO, _KEPT]]
    assert browsers[0].events[:2] == ["get_cookies", "set_cookies"]


async def test_cookies_chrome_still_has_are_left_alone(tmp_path, fake_launch):
    browsers, make = fake_launch
    fresher = Cookie(name="kept", value="new", domain="127.0.0.1", expires=4102444800.0)
    make["factory"] = lambda: _FakeBrowser(jar=[fresher])
    session_cookies.save(str(tmp_path), [_SSO, _KEPT])
    async with Session("s", path=str(tmp_path)).start():
        assert browsers[0].jar == [fresher, _SSO]  # only the missing one went back


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

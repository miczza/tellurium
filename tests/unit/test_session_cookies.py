"""The session keeps its cookie jar in cookies.json: Chrome drops the cookies
with no expiry on restart, and can lose the last one written before it closed.
Saved before Chrome closes; those Chrome lacks go back before the validators."""

from __future__ import annotations

import asyncio
import json
import sys
import threading

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


def test_a_too_nested_file_warns_and_is_set_aside(tmp_path):
    """A RecursionError is a bad file too: set aside, so the next close rewrites it."""
    (tmp_path / session_cookies.COOKIES_FILE).write_text("[" * 100_000)
    with pytest.warns(UserWarning, match="cookies.json"):
        assert session_cookies.read(str(tmp_path)) == ([], False)
    assert not (tmp_path / session_cookies.COOKIES_FILE).exists()
    aside = [p.name for p in tmp_path.iterdir() if p.name.startswith("cookies.json.bad-")]
    assert len(aside) == 1


def test_any_parsing_error_is_a_bad_file(tmp_path, monkeypatch):
    session_cookies.save(str(tmp_path), [_SSO])

    def broken(raw):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(session_cookies.Cookie, "from_json", staticmethod(broken))
    with pytest.warns(UserWarning, match="unexpected"):
        assert session_cookies.load(str(tmp_path)) == []


class _FakeBrowser:
    def __init__(
        self, jar=(), fail_read=False, hang_read=False, hang_write=False, late_read=0, late_write=0
    ):
        self.jar = list(jar)
        self.late_read = late_read  # the first read answers this late
        self.late_write = late_write  # writes are applied at once, answered this late
        self.fail_read = fail_read
        self.hang_read = hang_read
        self.hang_write = hang_write
        self.events: list[str] = []
        self.main_tab = object()

    async def get_cookies(self, domain=None):
        self.events.append("get_cookies")
        if self.hang_read:
            await asyncio.Event().wait()
        if self.fail_read:
            raise ConnectionError("chrome is gone")
        jar = list(self.jar)
        if self.late_read:
            late, self.late_read = self.late_read, 0
            await asyncio.sleep(late)
        return jar

    async def set_cookies(self, cookies):
        self.events.append("set_cookies")
        if self.hang_write:
            await asyncio.Event().wait()
        for cookie in cookies:  # the same name, domain, path and partition: replaced
            same = [i for i, c in enumerate(self.jar) if _ident(c) == _ident(cookie)]
            if same:
                self.jar[same[0]] = cookie
            else:
                self.jar.append(cookie)
        if self.late_write:
            await asyncio.sleep(self.late_write)

    async def close(self):
        self.events.append("close")


def _ident(c):
    return (c.name, c.domain, c.path, str(c.partition_key))


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


async def test_a_partitioned_cookie_is_not_the_unpartitioned_one(tmp_path, fake_launch):
    browsers, make = fake_launch
    plain = Cookie(name="c", value="1", domain="example.test", secure=True, same_site="None")
    chips = Cookie(
        name="c",
        value="2",
        domain="example.test",
        secure=True,
        same_site="None",
        partition_key={"topLevelSite": "https://other.test", "hasCrossSiteAncestor": True},
    )
    make["factory"] = lambda: _FakeBrowser(jar=[plain])
    session_cookies.save(str(tmp_path), [plain, chips])
    async with Session("s", path=str(tmp_path)).start():
        assert browsers[0].jar == [plain, chips]  # the partitioned one went back


async def test_a_failed_restore_does_not_lose_the_saved_cookies(tmp_path, fake_launch, monkeypatch):
    browsers, make = fake_launch
    monkeypatch.setattr(session_cookies, "TIMEOUT", 0.05)
    make["factory"] = lambda: _FakeBrowser(jar=[_KEPT], hang_write=True)
    session_cookies.save(str(tmp_path), [_SSO, _KEPT])
    async with Session("s", path=str(tmp_path)).start():
        pass
    assert browsers[0].events[-1] == "close"
    assert session_cookies.load(str(tmp_path)) == [_KEPT, _SSO]


async def test_a_start_cancelled_during_the_restore_keeps_the_saved_cookies(tmp_path, fake_launch):
    browsers, make = fake_launch
    make["factory"] = lambda: _FakeBrowser(hang_write=True)
    session_cookies.save(str(tmp_path), [_SSO])

    async def start():
        async with Session("s", path=str(tmp_path)).start():
            pass

    task = asyncio.create_task(start())
    while not browsers or "set_cookies" not in browsers[0].events:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert browsers[0].events[-1] == "close"
    assert session_cookies.load(str(tmp_path)) == [_SSO]


async def test_a_start_cancelled_while_reading_the_file_never_writes_it(
    tmp_path, fake_launch, monkeypatch
):
    """Cancelled before cookies.json is read: the close must not write the
    jar of a Chrome that never got the saved cookies over them."""
    browsers, _ = fake_launch
    session_cookies.save(str(tmp_path), [_SSO], at_close=True)
    reading, release = threading.Event(), threading.Event()
    real_read = session_cookies.read

    def slow_read(folder):
        reading.set()
        release.wait(5)
        return real_read(folder)

    monkeypatch.setattr(session_cookies, "read", slow_read)

    async def start():
        async with Session("s", path=str(tmp_path)).start():
            pass

    task = asyncio.create_task(start())
    try:
        while not reading.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
    assert browsers[0].events[-1] == "close"
    assert real_read(str(tmp_path)) == ([_SSO], True)


async def test_a_cookie_deleted_after_the_restore_stays_deleted(tmp_path, fake_launch):
    """A logout during the run: the restore was confirmed, so the close does
    not bring the cookie back."""
    session_cookies.save(str(tmp_path), [_SSO])
    async with Session("s", path=str(tmp_path)).start() as browser:
        browser.jar = []
    assert session_cookies.load(str(tmp_path)) == []


_OLD = Cookie(name="tok", value="old", domain="127.0.0.1", expires=4102444800.0)
_NEW = Cookie(name="tok", value="new", domain="127.0.0.1", expires=4102444800.0)


async def test_a_jar_saved_at_close_wins_over_an_older_copy_in_chrome(tmp_path, fake_launch):
    """A token rotated just before the close: the snapshot saw it, Chrome's
    cookie store did not commit it and comes back with the old one."""
    browsers, make = fake_launch
    make["factory"] = lambda: _FakeBrowser(jar=[_OLD])
    session_cookies.save(str(tmp_path), [_NEW], at_close=True)
    async with Session("s", path=str(tmp_path)).start():
        assert browsers[0].jar == [_NEW]
    assert session_cookies.load(str(tmp_path)) == [_NEW]


async def test_a_running_session_marks_its_file_as_not_saved_at_close(tmp_path, fake_launch):
    """If the process dies before the close, Chrome's copy may be the newer
    one: the next start only puts back what Chrome lacks."""
    session_cookies.save(str(tmp_path), [_SSO, _NEW], at_close=True)
    async with Session("s", path=str(tmp_path)).start():
        assert session_cookies.read(str(tmp_path)) == ([_SSO, _NEW], False)
    assert session_cookies.read(str(tmp_path))[1] is True


async def test_a_failed_restore_keeps_the_rotated_value(tmp_path, fake_launch, monkeypatch):
    browsers, make = fake_launch
    monkeypatch.setattr(session_cookies, "TIMEOUT", 0.05)
    make["factory"] = lambda: _FakeBrowser(jar=[_OLD, _KEPT], hang_write=True)
    session_cookies.save(str(tmp_path), [_SSO, _NEW], at_close=True)
    async with Session("s", path=str(tmp_path)).start():
        pass
    assert browsers[0].events[-1] == "close"
    saved = session_cookies.load(str(tmp_path))
    assert sorted(saved, key=lambda c: c.name) == [_KEPT, _SSO, _NEW]


async def test_a_cookie_changed_after_a_failed_restore_is_kept(tmp_path, fake_launch, monkeypatch):
    """The site set the cookie again during the run: Chrome's value is the live one."""
    browsers, make = fake_launch
    monkeypatch.setattr(session_cookies, "TIMEOUT", 0.05)
    make["factory"] = lambda: _FakeBrowser(jar=[_OLD], hang_write=True)
    session_cookies.save(str(tmp_path), [_NEW], at_close=True)
    newest = Cookie(name="tok", value="newest", domain="127.0.0.1", expires=4102444800.0)
    async with Session("s", path=str(tmp_path)).start() as browser:
        browser.jar = [newest]
    assert session_cookies.load(str(tmp_path)) == [newest]


async def test_a_start_on_a_too_nested_file_succeeds_and_rewrites_it(tmp_path, fake_launch):
    (tmp_path / session_cookies.COOKIES_FILE).write_text("[" * 100_000)
    with pytest.warns(UserWarning, match="cookies.json"):
        async with Session("s", path=str(tmp_path)).start() as browser:
            browser.jar = [_SSO]
    assert session_cookies.read(str(tmp_path)) == ([_SSO], True)


async def test_a_restore_answered_late_counts_and_a_deleted_cookie_stays_deleted(
    tmp_path, fake_launch, monkeypatch
):
    """Chrome took the cookies but answered after the timeout; the site then
    logged out: the close must not bring the cookie back."""
    browsers, make = fake_launch
    monkeypatch.setattr(session_cookies, "TIMEOUT", 0.05)
    make["factory"] = lambda: _FakeBrowser(late_write=0.2)
    session_cookies.save(str(tmp_path), [_SSO])
    async with Session("s", path=str(tmp_path)).start() as browser:
        assert browser.jar == [_SSO]
        await asyncio.sleep(0.3)  # the late answer arrives
        browser.jar = []  # logout
    assert session_cookies.load(str(tmp_path)) == []


async def test_a_cookie_chrome_had_and_the_site_deleted_stays_deleted_after_a_late_read(
    tmp_path, fake_launch, monkeypatch
):
    """The start's look at Chrome's jar timed out, its answer came later: a
    cookie Chrome had then and the site deleted is not put back."""
    browsers, make = fake_launch
    monkeypatch.setattr(session_cookies, "TIMEOUT", 0.05)
    make["factory"] = lambda: _FakeBrowser(jar=[_SSO], late_read=0.2)
    session_cookies.save(str(tmp_path), [_SSO], at_close=True)
    async with Session("s", path=str(tmp_path)).start() as browser:
        await asyncio.sleep(0.3)
        browser.jar = []
    assert session_cookies.load(str(tmp_path)) == []


async def test_a_restore_never_answered_is_not_left_running(tmp_path, fake_launch, monkeypatch):
    browsers, make = fake_launch
    monkeypatch.setattr(session_cookies, "TIMEOUT", 0.05)
    make["factory"] = lambda: _FakeBrowser(hang_write=True)
    session_cookies.save(str(tmp_path), [_SSO])
    before = asyncio.all_tasks()
    async with Session("s", path=str(tmp_path)).start():
        pass
    await asyncio.sleep(0)
    assert asyncio.all_tasks() - before == set()
    assert session_cookies.load(str(tmp_path)) == [_SSO]


async def test_save_from_a_thread_during_a_start_writes_the_current_jar(tmp_path, fake_launch):
    session = Session("s", path=str(tmp_path))
    async with session.start() as browser:
        browser.jar = [_SSO, _KEPT]
        await asyncio.to_thread(session.save)
        assert session_cookies.read(str(tmp_path)) == ([_SSO, _KEPT], False)
        browser.jar = [_KEPT]
    assert session_cookies.read(str(tmp_path)) == ([_KEPT], True)  # the close's is the last


async def test_save_on_the_loop_during_a_start_writes_the_current_jar(tmp_path, fake_launch):
    session = Session("s", path=str(tmp_path))
    async with session.start() as browser:
        browser.jar = [_SSO]
        await session.save()  # on the loop: awaitable, the jar is read from Chrome
        assert session_cookies.read(str(tmp_path)) == ([_SSO], False)
        browser.jar = [_KEPT]
        session.save()  # not awaited: the close waits for it, then writes its own
    assert session_cookies.read(str(tmp_path)) == ([_KEPT], True)
    assert session.save() is None  # closed: the jar the close read
    assert session_cookies.read(str(tmp_path)) == ([_KEPT], True)


async def test_a_live_save_keeps_the_cookies_a_failed_restore_left_pending(
    tmp_path, fake_launch, monkeypatch
):
    browsers, make = fake_launch
    monkeypatch.setattr(session_cookies, "TIMEOUT", 0.05)
    make["factory"] = lambda: _FakeBrowser(jar=[_KEPT], hang_write=True)
    session_cookies.save(str(tmp_path), [_SSO])
    session = Session("s", path=str(tmp_path))
    async with session.start():
        await session.save()
        assert session_cookies.load(str(tmp_path)) == [_KEPT, _SSO]


async def test_a_live_save_with_chrome_gone_keeps_the_file(tmp_path, fake_launch):
    session_cookies.save(str(tmp_path), [_SSO])
    session = Session("s", path=str(tmp_path))
    async with session.start() as browser:
        browser.fail_read = True
        await session.save()
        assert session_cookies.load(str(tmp_path)) == [_SSO]

"""The CI's factor on Chrome's answer deadlines reaches the code that waits."""

import asyncio
import json

import pytest

from tellurium.browser import process as process_module
from tellurium.browser import raw_chrome, robots
from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.transport._session import SessionRouter
from tests import timeout_scale


class _Silent(CDPTransport):
    """Takes every command, answers none."""

    async def send(self, data: bytes) -> None:
        json.loads(data.rstrip(b"\0"))

    async def recv(self) -> dict:
        await asyncio.sleep(3600)
        raise EOFError

    async def close(self) -> None:
        pass


class _Recorder:
    """A session that records the deadline of each command, then answers it."""

    def __init__(self):
        self.timeouts: dict[str, float] = {}

    async def send(self, method, params=None, *, timeout=None):
        self.timeouts[method] = timeout
        if method == "Network.loadNetworkResource":
            return {"resource": {"httpStatusCode": 200, "stream": "s"}}
        if method == "IO.read":
            return {"data": "", "eof": True}
        return {}


class _Frame:
    target_id = "t"

    def __init__(self, session):
        self.session = session


def test_without_the_variable_nothing_is_scaled(monkeypatch):
    monkeypatch.delenv(timeout_scale.ENV, raising=False)
    assert timeout_scale.factor() == 1.0
    assert timeout_scale.scaled(10) == 10


def test_the_variable_multiplies(monkeypatch):
    monkeypatch.setenv(timeout_scale.ENV, "3")
    assert timeout_scale.factor() == 3.0
    assert timeout_scale.scaled(10) == 30


@pytest.mark.parametrize("value", ["0", "-2", "three", "nan", "inf"])
def test_a_bad_factor_is_an_error_not_a_silent_one(monkeypatch, value):
    monkeypatch.setenv(timeout_scale.ENV, value)
    with pytest.raises(ValueError, match=timeout_scale.ENV):
        timeout_scale.factor()


async def test_the_router_default_reaches_a_send(monkeypatch):
    """A class default read at send time: the scaled value is the one that expires."""
    monkeypatch.setenv(timeout_scale.ENV, "0.001")  # 30 s -> 0.03 s
    with pytest.MonkeyPatch.context() as mp:
        timeout_scale.stretch(mp)
        router = SessionRouter(_Silent())
        with pytest.raises(asyncio.TimeoutError, match=r"0\.03"):
            await asyncio.wait_for(router.root.send("Target.attachToTarget", {}), 5)
    assert SessionRouter.default_timeout == 30.0  # given back


async def test_the_robots_deadlines_reach_the_download(monkeypatch):
    monkeypatch.setenv(timeout_scale.ENV, "3")
    session = _Recorder()
    with pytest.MonkeyPatch.context() as mp:
        timeout_scale.stretch(mp)
        await robots._load(_Frame(session), "http://site.test/robots.txt")
    assert session.timeouts["Network.loadNetworkResource"] == 30.0
    assert session.timeouts["IO.read"] == 30.0
    assert robots.FETCH_TIMEOUT == 10.0  # given back


def test_the_scaled_and_the_unscaled(monkeypatch):
    """What a test makes expire on purpose stays out of the list."""
    monkeypatch.setenv(timeout_scale.ENV, "3")
    with pytest.MonkeyPatch.context() as mp:
        timeout_scale.stretch(mp)
        assert SessionRouter.default_timeout == 90.0
        assert robots.FETCH_TIMEOUT == 30.0
        assert robots._OPEN_TIMEOUT == 15.0
        assert robots._CLOSE_TIMEOUT == 2.0


def test_the_close_grace_is_scaled(monkeypatch):
    """Chrome's own exit after Browser.close is an answer too: a runner stall
    past the 5 s grace ended in the signals (on Windows TerminateProcess with
    exit code 1, red 8 of R3)."""
    monkeypatch.setenv(timeout_scale.ENV, "3")
    with pytest.MonkeyPatch.context() as mp:
        timeout_scale.stretch(mp)
        assert process_module.CLOSE_GRACE == 15.0
        assert raw_chrome.CLOSE_GRACE == 15.0
    assert process_module.CLOSE_GRACE == raw_chrome.CLOSE_GRACE == 5.0  # given back


def test_the_session_cookie_calls_are_scaled(monkeypatch):
    """The login's jar reads and its CDP calls wait for Chrome: a stall of the
    Windows runner expired the 5 s cookie read and the test's 15 s wait
    for the login's cookie (run 42671685949)."""
    from tellurium.session import login_command, session, session_cookies

    monkeypatch.setenv(timeout_scale.ENV, "3")
    with pytest.MonkeyPatch.context() as mp:
        timeout_scale.stretch(mp)
        assert session_cookies.TIMEOUT == 15.0
        assert session.LIVE_SAVE_TIMEOUT == 30.0
        assert login_command.CALL_TIMEOUT == 15.0
    assert session_cookies.TIMEOUT == login_command.CALL_TIMEOUT == 5.0  # given back
    assert session.LIVE_SAVE_TIMEOUT == 10.0

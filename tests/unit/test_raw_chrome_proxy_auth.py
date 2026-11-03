"""RawChrome.answer_proxy_auth on a fake process and fake sessions: once per
Chrome, nothing left running after close()."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from tellurium.browser.process import BrowserProcess
from tellurium.browser.raw_chrome import RawChrome


class FakeForwarder:
    port = 4321
    credentials = ("tellurium", "the-secret")

    async def stop(self) -> None:
        pass


class FakeSession:
    """``send`` answers at once, except the methods in *hang* (never) and in
    *fail* (an error)."""

    def __init__(self, hang=(), fail=()) -> None:
        self.handlers: dict[str, list] = {}
        self.sent: list[str] = []
        self._hang, self._fail = set(hang), set(fail)

    async def send(self, method, params=None, timeout=None) -> dict:
        self.sent.append(method)
        if method in self._fail:
            raise RuntimeError(f"{method}: refused")
        if method in self._hang:
            await asyncio.Event().wait()
        return {}

    def on(self, event, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def off(self, event, handler) -> None:
        self.handlers[event].remove(handler)

    def wired(self) -> int:
        return sum(len(h) for h in self.handlers.values())

    def emit(self, event, params) -> None:
        for handler in list(self.handlers.get(event, [])):
            handler(params)


def _raw() -> RawChrome:
    proc = BrowserProcess()
    proc.forwarder = FakeForwarder()
    proc.process = SimpleNamespace(pid=4242, poll=lambda: 0)  # already exited
    return RawChrome(proc, SimpleNamespace(seed_used=None, proxy="http://u:p@proxy:8080"))


def _proxy_auth_tasks() -> list[asyncio.Task]:
    return [t for t in asyncio.all_tasks() if "ProxyAuth" in repr(t.get_coro())]


async def test_a_second_answer_is_refused_and_close_leaves_nothing_running():
    raw = _raw()
    first = FakeSession(hang={"Fetch.continueRequest"})
    await raw.answer_proxy_auth(first)
    first.emit("Fetch.requestPaused", {"requestId": "r1"})  # an answer in flight
    assert first.wired() == 2 and len(_proxy_auth_tasks()) == 1

    for again in (first, FakeSession()):
        with pytest.raises(RuntimeError, match="already answers"):
            await raw.answer_proxy_auth(again)
    assert first.sent.count("Fetch.enable") == 1

    await raw.close()
    assert first.wired() == 0 and not _proxy_auth_tasks()
    assert raw._proc.proxy_auth is None
    with pytest.raises(RuntimeError, match="closed"):
        await raw.answer_proxy_auth(FakeSession())


async def test_after_a_failed_answer_another_session_may_try_again():
    raw = _raw()
    refused = FakeSession(fail={"Fetch.enable"})
    with pytest.raises(RuntimeError, match="refused"):
        await raw.answer_proxy_auth(refused)
    assert refused.wired() == 0
    second = FakeSession()
    await raw.answer_proxy_auth(second)
    assert second.wired() == 2
    await raw.close()
    assert refused.wired() == second.wired() == 0 and not _proxy_auth_tasks()


async def test_without_credentials_it_does_nothing_even_twice():
    raw = _raw()
    raw._proc.forwarder = None
    session = FakeSession()
    await raw.answer_proxy_auth(session)
    await raw.answer_proxy_auth(session)
    assert session.sent == [] and raw._proc.proxy_auth is None
    await raw.close()

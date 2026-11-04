"""The multiplexer's answer to an authenticated proxy when a place goes wrong:
a failed attach or ``Fetch.enable`` while a Chrome opens, a cancellation in the
middle of it, an admin restart and a hung Chrome. Each Chrome takes its answer
with it; nothing is left behind (S1-B)."""

from __future__ import annotations

import asyncio
import os
import signal

import pytest

pytest.importorskip("websockets")

from tellurium.browser.raw_chrome import RawChrome  # noqa: E402
from tellurium.multiplexer import health  # noqa: E402
from tellurium.multiplexer.relay import Relay  # noqa: E402
from tests.integration.test_authenticated_proxy import (  # noqa: E402
    GOOD_AUTH,
    PASSWORD,
    USER,
    FakeProxy,
)
from tests.integration.test_multiplexer import (  # noqa: E402, F401 - autouse fixture
    _cdp,
    _client,
    _closed,
    _good,
    _port,
    _proxy_auth_tasks,
    serving,
    token_file,
)
from tests.integration.test_multiplexer_admin import _call  # noqa: E402
from tests.integration.test_raw_chrome import (  # noqa: E402, F401 - autouse fixture
    _alive,
    _profiles,
    _wait_until,
    private_tempdir,
)
from tests.platform_marks import needs_proc  # noqa: E402


@pytest.fixture
def launched(monkeypatch) -> list[tuple[RawChrome, int]]:
    """Every Chrome the places launch, with the port of its forwarder."""
    chromes: list[tuple[RawChrome, int]] = []
    start = RawChrome._start

    async def spy(cls, plan, chrome_log):
        raw = await start(plan, chrome_log)
        chromes.append((raw, raw._proc.forwarder.port))
        return raw

    monkeypatch.setattr(RawChrome, "_start", classmethod(spy))
    return chromes


def _broken(monkeypatch, method: str, instead: tuple[str, dict] | None) -> asyncio.Event:
    """The relay's first *method* goes wrong in Chrome: sent as *instead*, or
    never answered (None). The event is set when it happens."""
    call, hit = Relay.call, asyncio.Event()

    async def broken(self, name, params=None, **kw):
        if name == method and not hit.is_set():
            hit.set()
            if instead is None:
                await asyncio.Event().wait()
            name, params = instead
        return await call(self, name, params, **kw)

    monkeypatch.setattr(Relay, "call", broken)
    return hit


async def _released(chrome: RawChrome, forwarder_port: int) -> None:
    """*chrome* is gone with everything it owned."""
    proc = chrome._proc
    owned = ("process alive", "proxy_auth", "forwarder", "transport", "temp_profile")

    def left() -> list[str]:  # close() releases them one after the other
        alive = ["process alive"] if _alive(chrome.pid) else []
        return alive + [name for name in owned[1:] if getattr(proc, name) is not None]

    assert await _wait_until(lambda: not left(), 30), left()
    with pytest.raises(OSError):  # the forwarder no longer listens
        _, writer = await asyncio.open_connection("127.0.0.1", forwarder_port)
        writer.close()


async def _navigates(mux, proxy: FakeProxy, path: str) -> None:
    """A client's page reaches the upstream proxy with the real credentials."""
    async with _client(mux) as ws:
        await _cdp(ws, 1, "Target.createTarget", {"url": f"http://site.test/{path}"})
        line = f"GET http://site.test/{path} HTTP/1.1"
        assert await _wait_until(lambda: line in proxy.lines(), 20), proxy.lines()
    assert (line, GOOD_AUTH) in proxy.requests


def _url(proxy: FakeProxy) -> str:
    return f"http://{USER}:{PASSWORD}@127.0.0.1:{proxy.port}"


@pytest.mark.parametrize(
    "method, instead",
    [
        ("Target.attachToBrowserTarget", ("Target.noSuchMethod", {})),
        # Chrome refuses an empty pattern list with handleAuthRequests.
        ("Fetch.enable", ("Fetch.enable", {"handleAuthRequests": True, "patterns": []})),
    ],
    ids=["attach", "fetch-enable"],
)
@needs_proc
async def test_a_chrome_that_cannot_answer_the_proxy_is_a_failed_launch(
    monkeypatch,
    launched,
    private_tempdir,  # noqa: F811
    method,
    instead,
):
    hit = _broken(monkeypatch, method, instead)
    async with FakeProxy() as proxy, serving(1, warm=1, proxies=[_url(proxy)]) as mux:
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "ready", 60)
        assert hit.is_set()
        (failed, failed_port), (ready, _) = launched
        await _released(failed, failed_port)
        status = mux.status()
        assert status["launch_failures"] == 1 and status["slots"][0]["launches"] == 2
        assert status["slots"][0]["pid"] == ready.pid
        proc = ready._proc
        ready_dirs = {proc.temp_profile, proc.chrome_tmp, proc.downloads_tmp} - {None}
        assert {str(d) for d in _profiles(private_tempdir)} == ready_dirs  # the ready one's only
        await _navigates(mux, proxy, "after-a-failure")
    await _released(*launched[-1])
    assert not _proxy_auth_tasks()
    assert _profiles(private_tempdir) == []


@pytest.mark.parametrize("method", ["Target.attachToBrowserTarget", "Fetch.enable"])
@needs_proc
async def test_a_shutdown_while_a_chrome_opens_leaves_nothing_behind(
    monkeypatch,
    launched,
    private_tempdir,  # noqa: F811
    method,
):
    hit = _broken(monkeypatch, method, None)
    async with FakeProxy() as proxy, serving(1, warm=1, proxies=[_url(proxy)]):
        await asyncio.wait_for(hit.wait(), 60)
        assert len(launched) == 1
    # serve() cancelled (Ctrl-C) with the place in the middle of its _open.
    await _released(*launched[0])
    assert not _proxy_auth_tasks()
    assert _profiles(private_tempdir) == []


@needs_proc
async def test_an_admin_restart_gives_the_new_chrome_its_own_answer(
    launched,
    private_tempdir,  # noqa: F811
):
    async with FakeProxy() as proxy, serving(1, proxies=[_url(proxy)]) as mux:
        async with _client(mux) as ws:
            await _cdp(ws, 1, "Target.createTarget", {"url": "http://site.test/before"})
            assert await _wait_until(lambda: proxy.requests, 20)
            (old, old_port) = launched[0]
            old_auth = old._proc.proxy_auth
            status, _, _ = await _call(_port(mux), "POST", "/admin/slots/0/restart", _good(mux))
            assert status == 202
            code, _ = await _closed(ws)
            assert code == 1012
        await _released(old, old_port)
        assert not old_auth._active and not old_auth._tasks
        await _navigates(mux, proxy, "after-a-restart")
        assert launched[-1][0]._proc.proxy_auth not in (None, old_auth)
        assert mux.status()["slots"][0]["restarts"] == 1
    assert not _proxy_auth_tasks()


@needs_proc
async def test_a_hung_chrome_is_replaced_by_one_that_answers_again(
    monkeypatch,
    launched,
    private_tempdir,  # noqa: F811
):
    monkeypatch.setattr(health, "INTERVAL", 0.3)
    monkeypatch.setattr(health, "TIMEOUT", 0.7)
    async with FakeProxy() as proxy, serving(1, warm=1, proxies=[_url(proxy)]) as mux:
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "ready", 60)
        (hung, hung_port) = launched[0]
        hung_auth = hung._proc.proxy_auth
        os.kill(hung.pid, signal.SIGSTOP)
        await _released(hung, hung_port)
        assert not hung_auth._active and not hung_auth._tasks
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "ready", 60)
        assert mux.status()["hangs"] == 1
        await _navigates(mux, proxy, "after-a-hang")
    assert not _proxy_auth_tasks()
    assert _profiles(private_tempdir) == []

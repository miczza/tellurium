"""RawChrome: Chrome on its CDP pipe, without Browser, closed whatever happens.

Stock Chrome and local fixtures only. Processes are observed through /proc:
Chrome and every descendant (zygote, renderers, GPU, network service).
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
from pathlib import Path

import pytest

from tellurium.browser.launcher import LaunchError
from tellurium.browser.process import BrowserProcess
from tellurium.browser.raw_chrome import RawChrome
from tests.integration.test_authenticated_proxy import GOOD_AUTH, PASSWORD, USER, FakeProxy
from tests.platform_marks import needs_proc, needs_sh
from tests.private_temp import private_temp


@pytest.fixture(autouse=True)
def private_tempdir(monkeypatch, tmp_path_factory):
    """Profiles of this test alone (other tellurium runs share /tmp); short for
    Chrome's singleton socket path."""
    tmp_path_factory.getbasetemp()
    with private_temp(monkeypatch) as root:
        yield root


def _children(pid: int) -> set[int]:
    pids: set[int] = set()
    for path in glob.glob(f"/proc/{pid}/task/*/children"):
        try:
            pids.update(int(p) for p in Path(path).read_text().split())
        except OSError:
            pass
    return pids


def _descendants(pid: int) -> set[int]:
    found, todo = set(), [pid]
    while todo:
        for child in _children(todo.pop()) - found:
            found.add(child)
            todo.append(child)
    return found


def _alive(pid: int) -> bool:
    """Running, not a zombie waiting to be reaped."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] != "Z"


def _cmdline(pid: int) -> list[str]:
    """Arguments of *pid*. Chrome rewrites its argv into one space-separated
    string (its process title), so split on spaces too."""
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().decode().replace("\0", " ").split()
    except OSError:
        return []


def _profiles(root: Path) -> list[Path]:
    return sorted(root.glob("tellurium_*"))


async def _wait_until(predicate, timeout: float = 15.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


async def _call(
    raw: RawChrome, method: str, params: dict | None = None, id: int = 1, session: str = ""
) -> dict:
    """One CDP command straight on the pipe; events in between are dropped."""
    message = {"id": id, "method": method, "params": params or {}}
    if session:
        message["sessionId"] = session
    await raw.transport.send(json.dumps(message).encode() + b"\0")

    async def reply() -> dict:
        while True:
            answer = await raw.transport.recv()
            if answer.get("id") == id:
                return answer

    return await asyncio.wait_for(reply(), 15)


@needs_proc
async def test_cdp_answers_on_the_pipe_and_no_port_is_open(private_tempdir):
    async with RawChrome.launch(headless=True) as raw:
        answer = await _call(raw, "Browser.getVersion")
        assert "Chrome" in answer["result"]["product"]
        assert raw.alive

        # Renderers start with the first page: open one so they are checked too.
        await _call(raw, "Target.createTarget", {"url": "about:blank"}, id=2)
        processes = {raw.pid} | _descendants(raw.pid)
        assert len(processes) > 1
        lines = {pid: _cmdline(pid) for pid in processes}
        assert "--remote-debugging-pipe" in lines[raw.pid]
        for pid, line in lines.items():
            assert not [a for a in line if "remote-debugging-port" in a], (pid, line)
        assert not [a for a in lines[raw.pid] if a.startswith("--user-agent")]
        assert not [a for a in lines[raw.pid] if a.startswith("--load-extension")]


@needs_proc
async def test_close_leaves_no_process_and_no_profile(private_tempdir):
    raw = await RawChrome.launch(headless=True, viewport=(800, 600), languages=["it-IT", "it"])
    await _call(raw, "Target.createTarget", {"url": "about:blank"})
    processes = {raw.pid} | _descendants(raw.pid)
    line = _cmdline(raw.pid)
    assert "--window-size=800,600" in line
    assert "--accept-lang=it-IT,it" in line
    assert _profiles(private_tempdir)

    await asyncio.wait_for(raw.close(), 30)

    assert not raw.alive
    assert await _wait_until(lambda: not [p for p in processes if _alive(p)]), "orphans"
    assert not _profiles(private_tempdir), "the temporary profile was left behind"
    assert not list(private_tempdir.iterdir()), sorted(private_tempdir.iterdir())
    await asyncio.wait_for(raw.close(), 5)  # idempotent


async def test_close_asks_chrome_first(private_tempdir):
    """close() sends Browser.close on the pipe and Chrome exits on its own
    (status 0, its orderly exit), before any signal."""
    raw = await RawChrome.launch(headless=True)
    sent: list[bytes] = []
    send = raw.transport.send

    async def spy(data: bytes) -> None:
        sent.append(data)
        await send(data)

    raw.transport.send = spy
    process = raw._proc.process
    await asyncio.wait_for(raw.close(), 30)
    assert [json.loads(d[:-1])["method"] for d in sent] == ["Browser.close"]
    assert process.returncode == 0


@needs_proc
async def test_close_of_a_chrome_that_ignores_browser_close_escalates(private_tempdir, monkeypatch):
    import signal

    from tellurium.browser import raw_chrome

    monkeypatch.setattr(raw_chrome, "CLOSE_GRACE", 0.5)
    raw = await RawChrome.launch(headless=True)
    processes = {raw.pid} | _descendants(raw.pid)
    os.kill(raw.pid, signal.SIGSTOP)  # reads nothing, exits on nothing but SIGKILL
    loop = asyncio.get_running_loop()
    start = loop.time()
    await asyncio.wait_for(raw.close(), 30)
    assert loop.time() - start < 15
    assert not raw.alive
    assert await _wait_until(lambda: not [p for p in processes if _alive(p)]), "orphans"


@needs_proc
async def test_close_releases_everything_when_asking_fails_unexpectedly(
    private_tempdir, monkeypatch
):
    """An error of any kind while asking Chrome to close still closes the
    process and removes the profile, and is raised afterwards."""
    raw = await RawChrome.launch(headless=True)
    processes = {raw.pid} | _descendants(raw.pid)

    async def broken() -> None:
        raise RuntimeError("asking went wrong")

    monkeypatch.setattr(raw, "_ask_to_close", broken)
    with pytest.raises(RuntimeError, match="asking went wrong"):
        await asyncio.wait_for(raw.close(), 30)
    assert not raw.alive
    assert await _wait_until(lambda: not [p for p in processes if _alive(p)]), "orphans"
    assert not _profiles(private_tempdir), "the temporary profile was left behind"


async def test_alive_turns_false_when_chrome_dies(private_tempdir):
    async with RawChrome.launch(headless=True) as raw:
        os.kill(raw.pid, 9)
        assert await _wait_until(lambda: not raw.alive, 10)
    assert not _profiles(private_tempdir)


@needs_proc
async def test_cancelled_launch_leaves_nothing_behind(private_tempdir, monkeypatch):
    """Cancelled with Chrome already running and the forwarder up."""
    from tellurium.browser import proxy as proxy_mod

    stopped: list[object] = []
    real_stop = proxy_mod.ProxyForwarder.stop

    async def spy_stop(self):
        stopped.append(self)
        await real_stop(self)

    spawned: list[int] = []
    real_spawn = BrowserProcess.spawn

    async def spawn_then_hang(self, *args, **kwargs):
        transport = await real_spawn(self, *args, **kwargs)
        spawned.append(self.process.pid)
        await asyncio.sleep(3600)
        return transport

    monkeypatch.setattr(proxy_mod.ProxyForwarder, "stop", spy_stop)
    monkeypatch.setattr(BrowserProcess, "spawn", spawn_then_hang)
    task = asyncio.ensure_future(
        RawChrome.launch(headless=True, proxy="http://user:secret@127.0.0.1:9", geoip=False)
    )
    assert await _wait_until(lambda: spawned), "Chrome never started"
    await asyncio.sleep(0.5)  # let Chrome start its children
    processes = {spawned[0]} | _descendants(spawned[0])
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await _wait_until(lambda: not [p for p in processes if _alive(p)]), "orphans"
    assert not _profiles(private_tempdir), "the temporary profile was left behind"
    assert stopped, "the proxy forwarder was left running"


@needs_proc
async def test_a_mute_chrome_times_out_and_is_reaped(private_tempdir, tmp_path, monkeypatch):
    from tellurium.browser import raw_chrome

    script = tmp_path / "mute-chrome"
    script.write_text("#!/bin/sh\nexec sleep 60\n")
    script.chmod(0o755)
    monkeypatch.setattr(raw_chrome, "READY_TIMEOUT", 0.5)
    before = _children(os.getpid())

    with pytest.raises(asyncio.TimeoutError, match="Browser.getVersion"):
        await asyncio.wait_for(RawChrome.launch(executable=str(script)), 20)

    assert await _wait_until(lambda: _children(os.getpid()) <= before), "not reaped"
    assert not _profiles(private_tempdir)


@needs_sh
async def test_chrome_exiting_at_launch_is_explained(private_tempdir, tmp_path):
    script = tmp_path / "fake-chrome"
    script.write_text("#!/bin/sh\necho 'boom: libfoo.so missing' >&2\nexit 3\n")
    script.chmod(0o755)

    with pytest.raises(LaunchError, match="exit code 3") as info:
        await asyncio.wait_for(RawChrome.launch(executable=str(script)), 30)

    assert "boom: libfoo.so missing" in str(info.value)
    assert not _profiles(private_tempdir)


class _PipeSession:
    """What a client of RawChrome does: read the pipe itself and keep a browser
    session (``send``/``on``/``off``) for :meth:`RawChrome.answer_proxy_auth`."""

    def __init__(self, raw: RawChrome) -> None:
        self._raw = raw
        self._next = 0
        self._waiting: dict[int, asyncio.Future] = {}
        self._handlers: dict[str, list] = {}
        self.id = ""
        self._reader = asyncio.ensure_future(self._read())

    async def _read(self) -> None:
        while True:
            message = await self._raw.transport.recv()
            future = self._waiting.pop(message.get("id"), None)
            if future is not None and not future.done():
                future.set_result(message)
            elif "method" in message and message.get("sessionId") == self.id:
                for handler in list(self._handlers.get(message["method"], [])):
                    handler(message.get("params", {}))

    async def call(self, method: str, params=None, timeout=10.0, session: str = "") -> dict:
        self._next += 1
        future = asyncio.get_running_loop().create_future()
        self._waiting[self._next] = future
        message = {"id": self._next, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        await self._raw.transport.send(json.dumps(message).encode() + b"\0")
        reply = await asyncio.wait_for(future, timeout)
        assert "error" not in reply, reply
        return reply["result"]

    async def attach(self) -> _PipeSession:
        self.id = (await self.call("Target.attachToBrowserTarget"))["sessionId"]
        return self

    async def send(self, method: str, params=None, timeout=10.0) -> dict:
        return await self.call(method, params, timeout, session=self.id)

    def on(self, event: str, handler) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler) -> None:
        self._handlers.get(event, []).remove(handler)

    async def close(self) -> None:
        self._reader.cancel()
        await asyncio.wait([self._reader])


@needs_proc
async def test_credentials_stay_in_the_forwarder(private_tempdir):
    async with FakeProxy() as proxy:
        url = f"http://{USER}:{PASSWORD}@127.0.0.1:{proxy.port}"
        async with RawChrome.launch(headless=True, proxy=url, geoip=False, seed=5) as raw:
            assert raw.proxy == url
            assert raw.seed is None  # stock Chrome takes no seed
            assert raw.needs_proxy_auth
            line = _cmdline(raw.pid)
            servers = [a for a in line if a.startswith("--proxy-server=")]
            assert len(servers) == 1
            host, _, port = servers[0].removeprefix("--proxy-server=http://").partition(":")
            assert host == "127.0.0.1" and int(port) != proxy.port
            assert not [a for a in line if PASSWORD in a]
            assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in line

            # Whoever reads the pipe answers the forwarder's challenge through
            # RawChrome, on a browser session of its own, before navigating.
            session = await _PipeSession(raw).attach()
            try:
                await raw.answer_proxy_auth(session)
                await session.call("Target.createTarget", {"url": "http://site.test/"})
                assert await _wait_until(lambda: proxy.requests, 15), "nothing reached the proxy"
            finally:
                await session.close()
            assert proxy.requests[0] == ("GET http://site.test/ HTTP/1.1", GOOD_AUTH)
            assert raw._proc.proxy_auth is not None
        # close() stopped the answer with Chrome: nothing of it is left running.
        assert raw._proc.proxy_auth is None
        assert not [t for t in asyncio.all_tasks() if "ProxyAuth" in repr(t.get_coro())]


async def test_without_credentials_there_is_nothing_to_answer(private_tempdir):
    async with RawChrome.launch(headless=True, geoip=False) as raw:
        assert not raw.needs_proxy_auth
        await raw.answer_proxy_auth(object())  # no forwarder: nothing happens
        assert raw._proc.proxy_auth is None


async def test_cancelled_geoip_lookups_do_not_starve_close(private_tempdir):
    """A dead proxy that does not refuse, many launches cancelled during GeoIP:
    each returns at once, and another Chrome still closes in time."""
    from tests.unit.test_launch_plan import SilentProxy

    launches = 40
    async with SilentProxy() as proxy:
        # Without credentials: no forwarder whose closing would end the lookups.
        url = f"http://127.0.0.1:{proxy.port}"
        tasks = [asyncio.ensure_future(RawChrome.launch(proxy=url)) for _ in range(launches)]
        # All at once: none waits for a thread another lookup holds.
        assert await _wait_until(lambda: proxy.accepted >= launches, 4), proxy.accepted
        started = asyncio.get_running_loop().time()
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(isinstance(r, asyncio.CancelledError) for r in results), results
        assert asyncio.get_running_loop().time() - started < 5
        assert not _profiles(private_tempdir)
        # The lookups given up on run on, but not on the executor close() needs.
        await asyncio.wait_for(asyncio.to_thread(lambda: None), 1)

        raw = await asyncio.wait_for(RawChrome.launch(headless=True), 30)
        started = asyncio.get_running_loop().time()
        await raw.close()
        assert asyncio.get_running_loop().time() - started < 10
        assert not raw.alive
    assert not _profiles(private_tempdir)


async def _page_time_zone(raw: RawChrome) -> str:
    target = await _call(raw, "Target.createTarget", {"url": "about:blank"}, id=11)
    attached = await _call(
        raw,
        "Target.attachToTarget",
        {"targetId": target["result"]["targetId"], "flatten": True},
        id=12,
    )
    session = attached["result"]["sessionId"]
    expression = "Intl.DateTimeFormat().resolvedOptions().timeZone"
    answer = await _call(
        raw, "Runtime.evaluate", {"expression": expression}, id=13, session=session
    )
    return answer["result"]["result"]["value"]


async def test_stock_chrome_takes_the_manual_time_zone(private_tempdir):
    async with RawChrome.launch(headless=True, timezone="Pacific/Chatham") as raw:
        assert await _page_time_zone(raw) == "Pacific/Chatham"


@needs_proc
async def test_stock_chrome_takes_the_time_zone_of_the_exit_ip(private_tempdir, monkeypatch):
    from tellurium.stealth import geoip
    from tellurium.stealth.geoip import GeoResult

    japan = GeoResult(country="JP", timezone="Asia/Tokyo", languages=["ja-JP", "en"])
    monkeypatch.setattr(geoip, "exit_geo", lambda *a, **kw: japan)
    async with RawChrome.launch(headless=True, proxy="http://127.0.0.1:9") as raw:
        assert await _page_time_zone(raw) == "Asia/Tokyo"
        assert "--accept-lang=ja-JP,en" in _cmdline(raw.pid)


@pytest.fixture
def stopped_forwarders(monkeypatch) -> list:
    from tellurium.browser import proxy as proxy_mod

    stopped: list[object] = []
    real_stop = proxy_mod.ProxyForwarder.stop

    async def spy_stop(self):
        stopped.append(self)
        await real_stop(self)

    monkeypatch.setattr(proxy_mod.ProxyForwarder, "stop", spy_stop)
    return stopped


async def _cancel(task: asyncio.Future) -> float:
    """Cancel *task*; seconds until it is over."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 30)
    return loop.time() - started


@needs_proc
async def test_launch_cancelled_while_the_forwarder_starts(
    private_tempdir, monkeypatch, stopped_forwarders
):
    from tellurium.browser import proxy as proxy_mod

    real_start = proxy_mod.ProxyForwarder.start
    started: list[int] = []

    async def start_then_hang(self):
        await real_start(self)
        started.append(self.port)
        await asyncio.sleep(3600)

    monkeypatch.setattr(proxy_mod.ProxyForwarder, "start", start_then_hang)
    before = _children(os.getpid())
    task = asyncio.ensure_future(
        RawChrome.launch(proxy="http://user:secret@127.0.0.1:9", geoip=False)
    )
    assert await _wait_until(lambda: started), "the forwarder never started"
    assert await _cancel(task) < 5
    assert stopped_forwarders, "the proxy forwarder was left running"
    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", started[0])
    assert _children(os.getpid()) <= before
    assert not _profiles(private_tempdir)


@needs_proc
async def test_launch_cancelled_during_geoip(private_tempdir, stopped_forwarders):
    from tests.unit.test_launch_plan import SilentProxy

    before = _children(os.getpid())
    async with SilentProxy() as proxy:
        url = f"http://{USER}:{PASSWORD}@127.0.0.1:{proxy.port}"
        task = asyncio.ensure_future(RawChrome.launch(proxy=url))
        assert await _wait_until(lambda: proxy.accepted), "the lookup never started"
        assert _profiles(private_tempdir)
        assert await _cancel(task) < 5
    assert stopped_forwarders, "the proxy forwarder was left running"
    assert _children(os.getpid()) <= before, "Chrome was started anyway"
    assert not _profiles(private_tempdir)


@needs_proc
async def test_launch_cancelled_while_waiting_for_chrome_to_answer(private_tempdir, tmp_path):
    script = tmp_path / "mute-chrome"
    script.write_text("#!/bin/sh\nexec sleep 60\n")
    script.chmod(0o755)
    before = _children(os.getpid())
    task = asyncio.ensure_future(RawChrome.launch(executable=str(script)))
    assert await _wait_until(lambda: _children(os.getpid()) - before), "Chrome never started"
    (chrome,) = _children(os.getpid()) - before
    await asyncio.sleep(0.2)  # into the wait for Browser.getVersion
    assert await _cancel(task) < 15
    assert await _wait_until(lambda: not _alive(chrome)), "not reaped"
    assert not _profiles(private_tempdir)

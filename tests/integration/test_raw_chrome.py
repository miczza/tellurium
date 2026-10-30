"""RawChrome: Chrome on its CDP pipe, without Browser, closed whatever happens.

Stock Chrome and local fixtures only. Processes are observed through /proc:
Chrome and every descendant (zygote, renderers, GPU, network service).
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from tellurium.browser.launcher import LaunchError
from tellurium.browser.process import BrowserProcess
from tellurium.browser.raw_chrome import RawChrome
from tests.integration.test_authenticated_proxy import GOOD_AUTH, PASSWORD, USER, FakeProxy

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="uses /proc to observe processes"
)


@pytest.fixture(autouse=True)
def private_tempdir(monkeypatch, tmp_path_factory):
    """Profiles of this test alone (other tellurium runs share /tmp); short for
    Chrome's singleton socket path."""
    tmp_path_factory.getbasetemp()
    root = Path(tempfile.mkdtemp(prefix="tlr", dir="/tmp"))
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    monkeypatch.setenv("TMPDIR", str(root))
    yield root
    shutil.rmtree(root, ignore_errors=True)


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


async def _call(raw: RawChrome, method: str, params: dict | None = None, id: int = 1) -> dict:
    """One CDP command straight on the pipe; events in between are dropped."""
    message = {"id": id, "method": method, "params": params or {}}
    await raw.transport.send(json.dumps(message).encode() + b"\0")

    async def reply() -> dict:
        while True:
            answer = await raw.transport.recv()
            if answer.get("id") == id:
                return answer

    return await asyncio.wait_for(reply(), 15)


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


async def test_alive_turns_false_when_chrome_dies(private_tempdir):
    async with RawChrome.launch(headless=True) as raw:
        os.kill(raw.pid, 9)
        assert await _wait_until(lambda: not raw.alive, 10)
    assert not _profiles(private_tempdir)


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

    async def spawn_then_hang(self, *args):
        transport = await real_spawn(self, *args)
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


async def test_chrome_exiting_at_launch_is_explained(private_tempdir, tmp_path):
    script = tmp_path / "fake-chrome"
    script.write_text("#!/bin/sh\necho 'boom: libfoo.so missing' >&2\nexit 3\n")
    script.chmod(0o755)

    with pytest.raises(LaunchError, match="exit code 3") as info:
        await asyncio.wait_for(RawChrome.launch(executable=str(script)), 30)

    assert "boom: libfoo.so missing" in str(info.value)
    assert not _profiles(private_tempdir)


async def test_credentials_stay_in_the_forwarder(private_tempdir):
    async with FakeProxy() as proxy:
        url = f"http://{USER}:{PASSWORD}@127.0.0.1:{proxy.port}"
        async with RawChrome.launch(headless=True, proxy=url, geoip=False, seed=5) as raw:
            assert raw.proxy == url
            assert raw.seed == 5
            line = _cmdline(raw.pid)
            servers = [a for a in line if a.startswith("--proxy-server=")]
            assert len(servers) == 1
            host, _, port = servers[0].removeprefix("--proxy-server=http://").partition(":")
            assert host == "127.0.0.1" and int(port) != proxy.port
            assert not [a for a in line if PASSWORD in a]
            assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in line

            await _call(raw, "Target.createTarget", {"url": "http://site.test/"})
            assert await _wait_until(lambda: proxy.requests), "nothing reached the proxy"
            assert proxy.requests[0][1] == GOOD_AUTH

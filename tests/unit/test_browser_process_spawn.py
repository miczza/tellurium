"""BrowserProcess.spawn: what Chrome is started with, the wait for its first
answer, the second start for the User-Agent, and the portable kill."""

from __future__ import annotations

import asyncio
import json
import subprocess

import pytest

from tellurium.browser import process as process_module
from tellurium.browser.process import BrowserProcess


class _Chrome:
    """Popen stand-in: alive until killed or asked to close."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("chrome", timeout)
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class _Transport:
    """Answers Browser.getVersion with *product*; Browser.close ends its Chrome."""

    def __init__(self, chrome: _Chrome, product: str | None) -> None:
        self.chrome = chrome
        self.product = product
        self.sent: list[dict] = []
        self.closed = False
        self._replies: asyncio.Queue = asyncio.Queue()

    async def start(self) -> None:
        pass

    async def send(self, data: bytes) -> None:
        message = json.loads(data[:-1])
        self.sent.append(message)
        if message["method"] == "Browser.getVersion" and self.product is not None:
            await self._replies.put({"method": "Target.noise", "params": {}})
            await self._replies.put({"id": message["id"], "result": {"product": self.product}})
        elif message["method"] == "Browser.close":
            self.chrome.returncode = 0

    async def recv(self) -> dict:
        return await self._replies.get()

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def started(monkeypatch):
    """Each start: (path, flags, output, env, chrome, transport)."""
    starts = _Starts()
    product = {"value": "HeadlessChrome/157.0.7400.12"}

    def launch(chrome_path, flags, output, env):
        chrome = _Chrome()
        starts.append([chrome_path, list(flags), output, dict(env), chrome, None])
        return chrome, 7, 8

    def transport(read_fd, write_fd):
        chrome = starts[-1][4]
        starts[-1][5] = _Transport(chrome, product["value"])
        return starts[-1][5]

    monkeypatch.setattr(process_module, "launch_chrome", launch)
    monkeypatch.setattr(process_module, "create_transport", transport)
    monkeypatch.setattr(process_module, "OutputTail", lambda fd: _Tail(fd))
    starts.product = product
    return starts


class _Starts(list):
    product: dict


class _Tail:
    def __init__(self, fd: int) -> None:
        import os

        os.close(fd)

    def join(self, timeout: float) -> None:
        pass

    def text(self) -> str:
        return ""


@pytest.mark.parametrize(
    "platform, names",
    [("linux", {"TMPDIR"}), ("darwin", {"TMPDIR"}), ("win32", {"TMP", "TEMP"})],
)
async def test_chrome_gets_a_temp_dir_of_ours_and_the_launch_env(
    started, monkeypatch, platform, names
):
    monkeypatch.setattr(process_module.sys, "platform", platform)
    proc = BrowserProcess()
    try:
        await proc.spawn("/x/chrome", ["--a"], None, {"TZ": "Europe/Rome"})
        (_, flags, _, env, _, _), *_ = started
        assert flags == ["--a"]
        assert env["TZ"] == "Europe/Rome"
        assert {name: env[name] for name in names} == dict.fromkeys(names, proc.chrome_tmp)
    finally:
        await proc.close()


@pytest.mark.parametrize("platform, added", [("win32", True), ("linux", False)])
async def test_a_chrome_log_on_windows_turns_on_chrome_logging(
    started, monkeypatch, tmp_path, platform, added
):
    monkeypatch.setattr(process_module.sys, "platform", platform)
    proc = BrowserProcess()
    try:
        await proc.spawn("/x/chrome", ["--a"], tmp_path / "chrome.log", None)
        (_, flags, output, *_), *_ = started
        assert flags == (["--a", "--enable-logging=stderr"] if added else ["--a"])
        assert output == proc._log_file.fileno()
    finally:
        await proc.close()


async def test_logging_chosen_by_the_caller_is_kept_on_windows(started, monkeypatch, tmp_path):
    monkeypatch.setattr(process_module.sys, "platform", "win32")
    proc = BrowserProcess()
    try:
        await proc.spawn("/x/chrome", ["--enable-logging", "--v=1"], tmp_path / "c.log", None)
        assert started[0][1] == ["--enable-logging", "--v=1"]
    finally:
        await proc.close()


async def test_spawn_returns_once_chrome_answers(started):
    proc = BrowserProcess()
    try:
        transport = await proc.spawn("/x/chrome", [], None)
        assert [m["method"] for m in transport.sent] == ["Browser.getVersion"]
    finally:
        await proc.close()


async def test_a_mute_chrome_fails_the_spawn_naming_the_command(started, monkeypatch):
    started.product["value"] = None
    monkeypatch.setattr(process_module, "READY_TIMEOUT", 0.2)
    proc = BrowserProcess()
    try:
        with pytest.raises(TimeoutError, match="Browser.getVersion got no reply"):
            await proc.spawn("/x/chrome", [], None)
    finally:
        await proc.close()


async def test_the_relaunch_closes_the_first_chrome_and_starts_one_with_the_new_flags(started):
    proc = BrowserProcess()
    products: list[str] = []
    proc.relaunch_with = lambda product: products.append(product) or ["--b", "--user-agent=X"]
    try:
        transport = await proc.spawn("/x/chrome", ["--a"], None, {"TZ": "UTC"})
        first, second = started
        assert products == ["HeadlessChrome/157.0.7400.12"]
        assert [m["method"] for m in first[5].sent] == ["Browser.getVersion", "Browser.close"]
        assert first[5].closed and first[4].returncode == 0
        assert second[1] == ["--b", "--user-agent=X"] and second[3]["TZ"] == "UTC"
        assert second[3]["TMPDIR" if "TMPDIR" in second[3] else "TMP"] == proc.chrome_tmp
        assert transport is second[5] is proc.transport and proc.process is second[4]
        assert proc.relaunch_with is None
    finally:
        await proc.close()


async def test_a_relaunch_without_new_flags_starts_the_same_command_line(started):
    proc = BrowserProcess()
    proc.relaunch_with = lambda product: None
    try:
        await proc.spawn("/x/chrome", ["--a"], None)
        assert [s[1] for s in started] == [["--a"], ["--a"]]
    finally:
        await proc.close()


def test_kill_ends_a_running_chrome_and_ignores_an_exited_one():
    proc = BrowserProcess()
    proc.kill()  # nothing started: nothing to do
    proc.process = _Chrome()
    proc.kill()
    assert proc.process.killed and proc.process.returncode == -9
    proc.process.killed = False
    proc.kill()
    assert not proc.process.killed

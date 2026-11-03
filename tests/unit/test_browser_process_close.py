"""BrowserProcess.close() releases every resource, even when a step fails or
the closing task is cancelled again and again (rollback of a cancelled launch)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import time

import pytest

from tellurium.browser import process as process_module
from tellurium.browser.process import BrowserProcess


class _SlowProcess:
    """Popen stand-in that takes a while to exit after terminate()."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self._exited = threading.Event()

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        def exit_later() -> None:
            time.sleep(0.3)
            self.returncode = -15
            self._exited.set()

        threading.Thread(target=exit_later, daemon=True).start()

    kill = terminate

    def wait(self, timeout=None):
        if not self._exited.wait(timeout):
            raise subprocess.TimeoutExpired("chrome", timeout)
        return self.returncode


class _Transport:
    def __init__(self, fail: bool = False, on_send=None) -> None:
        self.closed = False
        self.sent: list[dict] = []
        self._fail = fail
        self._on_send = on_send

    async def send(self, data: bytes) -> None:
        assert data.endswith(b"\0")
        self.sent.append(json.loads(data[:-1]))
        if self._on_send is not None:
            self._on_send()

    async def close(self) -> None:
        self.closed = True
        if self._fail:
            raise OSError("boom")


class _Forwarder:
    stopped = False

    async def stop(self) -> None:
        await asyncio.sleep(0.05)
        self.stopped = True


def _owner(tmp_path, transport: _Transport) -> BrowserProcess:
    owner = BrowserProcess()
    owner.process = _SlowProcess()
    owner.transport = transport
    owner.forwarder = _Forwarder()
    owner.temp_profile = str(tmp_path / "profile")
    (tmp_path / "profile").mkdir()
    owner.downloads_tmp = str(tmp_path / "downloads")
    (tmp_path / "downloads").mkdir()
    return owner


async def test_a_failing_step_does_not_skip_the_rest(tmp_path):
    forwarder_owner = _owner(tmp_path, _Transport(fail=True))
    forwarder = forwarder_owner.forwarder

    await forwarder_owner.close()

    assert forwarder.stopped
    assert not (tmp_path / "profile").exists()


async def test_close_finishes_across_repeated_cancellation(tmp_path):
    transport = _Transport()
    owner = _owner(tmp_path, transport)
    process, forwarder = owner.process, owner.forwarder

    closing = asyncio.ensure_future(owner.close())
    for _ in range(4):
        await asyncio.sleep(0.05)
        closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing

    assert process.returncode is not None, "Chrome was not reaped"
    assert transport.closed
    assert forwarder.stopped
    assert not (tmp_path / "profile").exists()
    assert not (tmp_path / "downloads").exists()


async def test_the_cdp_reader_is_stopped_first(tmp_path, monkeypatch):
    monkeypatch.setattr(process_module, "CLOSE_GRACE", 0.1)
    owner = _owner(tmp_path, _Transport())
    reader = asyncio.ensure_future(asyncio.Event().wait())
    owner.reader = reader

    await owner.close()

    assert reader.cancelled()


class _ObedientProcess(_SlowProcess):
    """Exits as soon as it gets Browser.close; counts the signals it gets."""

    signals = 0

    def terminate(self) -> None:
        self.signals += 1
        super().terminate()

    kill = terminate

    def exit_now(self) -> None:
        self.returncode = 0
        self._exited.set()


def _reading(owner: BrowserProcess) -> None:
    owner.reader = asyncio.ensure_future(asyncio.Event().wait())


async def test_chrome_is_asked_to_close_before_any_signal(tmp_path):
    process = _ObedientProcess()
    owner = _owner(tmp_path, _Transport(on_send=process.exit_now))
    owner.process = process
    transport = owner.transport
    _reading(owner)

    await owner.close()

    assert [m["method"] for m in transport.sent] == ["Browser.close"]
    assert process.signals == 0
    assert process.returncode == 0


async def test_a_chrome_ignoring_browser_close_gets_the_signals(tmp_path, monkeypatch):
    monkeypatch.setattr(process_module, "CLOSE_GRACE", 0.2)
    owner = _owner(tmp_path, _Transport())
    process = owner.process
    transport = owner.transport
    _reading(owner)
    loop = asyncio.get_running_loop()
    start = loop.time()

    await owner.close()

    assert [m["method"] for m in transport.sent] == ["Browser.close"]
    assert process.returncode == -15
    assert loop.time() - start < 0.2 + 0.3 + 1.0


def test_chrome_gets_five_seconds_to_close():
    assert process_module.CLOSE_GRACE == 5.0


@pytest.mark.parametrize("reader", ["none", "ended"])
async def test_a_broken_pipe_skips_browser_close(tmp_path, reader):
    owner = _owner(tmp_path, _Transport())
    transport = owner.transport
    if reader == "ended":
        owner.reader = asyncio.ensure_future(asyncio.sleep(0))
        await owner.reader
    loop = asyncio.get_running_loop()
    start = loop.time()

    await owner.close()

    assert transport.sent == []
    assert loop.time() - start < 2.0


async def test_a_failing_send_goes_straight_to_the_signals(tmp_path):
    def fail() -> None:
        raise ConnectionError("pipe closed")

    owner = _owner(tmp_path, _Transport(on_send=fail))
    process = owner.process
    _reading(owner)
    loop = asyncio.get_running_loop()
    start = loop.time()

    await owner.close()

    assert process.returncode == -15
    assert loop.time() - start < 2.0


# --- the answer to the forwarder's challenge (S1) ---------------------------


class _Session:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.handlers: dict[str, list] = {}

    async def send(self, method, params=None, timeout=None):
        self.sent.append(method)
        return {}

    def on(self, event, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def off(self, event, handler) -> None:
        self.handlers[event].remove(handler)


async def test_no_forwarder_no_fetch():
    owner, session = BrowserProcess(), _Session()
    await owner.answer_proxy_auth(session)
    assert owner.proxy_auth is None and session.sent == []


async def test_the_proxy_auth_is_owned_and_stopped_by_close(tmp_path):
    from types import SimpleNamespace

    owner = _owner(tmp_path, _Transport())
    owner.forwarder.port = 41234
    owner.forwarder.credentials = ("tellurium", "x" * 43)
    session = _Session()
    await owner.answer_proxy_auth(session)
    auth = owner.proxy_auth
    assert session.sent == ["Fetch.enable"]
    stopped = []
    real_stop = auth.stop

    async def spy_stop():
        stopped.append(SimpleNamespace(forwarder_stopped=owner.forwarder is None))
        await real_stop()

    auth.stop = spy_stop
    closing = asyncio.ensure_future(owner.close())
    for _ in range(3):
        await asyncio.sleep(0.05)
        closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert len(stopped) == 1 and not stopped[0].forwarder_stopped
    assert owner.proxy_auth is None
    assert not any(session.handlers.values())

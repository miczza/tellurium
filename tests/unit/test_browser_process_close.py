"""BrowserProcess.close() releases every resource, even when a step fails or
the closing task is cancelled again and again (rollback of a cancelled launch)."""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time

import pytest

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
    def __init__(self, fail: bool = False) -> None:
        self.closed = False
        self._fail = fail

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


async def test_the_cdp_reader_is_stopped_first(tmp_path):
    owner = _owner(tmp_path, _Transport())
    reader = asyncio.ensure_future(asyncio.Event().wait())
    owner.reader = reader

    await owner.close()

    assert reader.cancelled()

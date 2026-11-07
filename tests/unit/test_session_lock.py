"""SessionLock: one holder per session folder, across processes, with its PID."""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

from tellurium import SessionBusyError
from tellurium.session import SessionError
from tellurium.session.lock import SessionLock, lock_file


def test_busy_error_is_exported_and_a_session_error():
    import tellurium.session

    assert tellurium.session.SessionBusyError is SessionBusyError
    assert issubclass(SessionBusyError, SessionError)


def test_second_holder_gets_busy_error_with_the_pid(tmp_path):
    first = SessionLock(str(tmp_path))
    first.acquire()
    try:
        with pytest.raises(SessionBusyError) as info:
            SessionLock(str(tmp_path)).acquire()
        assert info.value.pid == os.getpid()
        assert str(os.getpid()) in str(info.value)
        assert info.value.path == str(tmp_path)
    finally:
        first.release()


def test_release_frees_the_folder(tmp_path):
    first = SessionLock(str(tmp_path))
    first.acquire()
    first.release()
    first.release()  # twice is harmless
    second = SessionLock(str(tmp_path))
    second.acquire()
    second.release()


def test_lock_file_holds_the_pid_and_is_private(tmp_path):
    lock = SessionLock(str(tmp_path))
    lock.acquire()
    try:
        path = Path(lock_file(str(tmp_path)))
        assert path.read_text().strip() == str(os.getpid())
        if sys.platform != "win32":
            assert path.stat().st_mode & 0o777 == 0o600
    finally:
        lock.release()


def test_holder_reports_the_pid_without_taking_the_lock(tmp_path):
    assert SessionLock.holder(str(tmp_path / "missing")) is None
    assert SessionLock.holder(str(tmp_path)) is None
    lock = SessionLock(str(tmp_path))
    lock.acquire()
    try:
        assert SessionLock.holder(str(tmp_path)) == os.getpid()
    finally:
        lock.release()
    assert SessionLock.holder(str(tmp_path)) is None


def test_the_lock_is_beside_the_folder_and_acquire_makes_only_its_parent(tmp_path):
    lock = SessionLock(str(tmp_path / "a" / "B"))
    lock.acquire()
    lock.release()
    assert lock_file(str(tmp_path / "a" / "B")) == str(tmp_path / "a" / ".b.lock")
    assert (tmp_path / "a" / ".b.lock").exists()
    assert not (tmp_path / "a" / "B").exists()


def test_a_lock_file_inside_the_folder_from_earlier_versions_is_ignored(tmp_path):
    folder = tmp_path / "s"
    folder.mkdir()
    (folder / "session.lock").write_text("4242\n")
    assert SessionLock.holder(str(folder)) is None
    lock = SessionLock(str(folder))
    lock.acquire()
    lock.release()


def test_acquire_twice_on_one_lock_is_an_error(tmp_path):
    lock = SessionLock(str(tmp_path))
    lock.acquire()
    try:
        with pytest.raises(RuntimeError):
            lock.acquire()
    finally:
        lock.release()


class _FakeMsvcrt(types.ModuleType):
    """msvcrt.locking: byte ranges of one file shared by every handle."""

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self):
        super().__init__("msvcrt")
        self.held: dict[tuple[int, int], int] = {}  # (inode, offset) -> fd
        self.calls: list[tuple[int, int, int]] = []

    def locking(self, fd, mode, nbytes):
        key = (os.fstat(fd).st_ino, os.lseek(fd, 0, os.SEEK_CUR))
        self.calls.append((mode, key[1], nbytes))
        if mode == self.LK_NBLCK:
            if key in self.held:
                raise OSError(36, "Resource deadlock avoided")
            self.held[key] = fd
        elif mode == self.LK_UNLCK:
            self.held.pop(key, None)


def test_windows_backend_uses_msvcrt_locking(tmp_path, monkeypatch):
    fake = _FakeMsvcrt()
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(sys, "platform", "win32")

    first = SessionLock(str(tmp_path))
    first.acquire()
    assert fake.held  # the lock went through msvcrt, not fcntl
    with pytest.raises(SessionBusyError) as info:
        SessionLock(str(tmp_path)).acquire()
    assert info.value.pid == os.getpid()  # the PID is outside the locked byte
    first.release()
    assert not fake.held
    assert all(nbytes == 1 for _, _, nbytes in fake.calls)
    second = SessionLock(str(tmp_path))
    second.acquire()
    second.release()


def _probed_for_a_moment(path, seconds=0.02):
    """Hold *path*'s lock file as a probe does (shared, from another handle)
    and let it go after *seconds*."""
    import fcntl
    import threading

    fd = os.open(lock_file(path), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)

    def let_go():
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    timer = threading.Timer(seconds, let_go)
    timer.start()
    return timer


@pytest.fixture
def fake_launch(monkeypatch):
    import tellurium

    class _Browser:
        async def get_cookies(self, domain=None):
            return []

        async def close(self):
            pass

    async def launch(**kwargs):
        return _Browser()

    monkeypatch.setattr(tellurium.Browser, "launch", launch)


@pytest.mark.skipif(sys.platform == "win32", reason="flock")
async def test_a_probe_does_not_make_a_start_busy(tmp_path, fake_launch):
    from tellurium import Session

    Path(lock_file(str(tmp_path))).write_text("4242\n")  # a holder long gone
    timer = _probed_for_a_moment(str(tmp_path))
    try:
        async with Session("s", path=str(tmp_path)).start():
            pass
    finally:
        timer.join()


@pytest.mark.skipif(sys.platform == "win32", reason="flock")
def test_a_probe_does_not_make_another_probe_see_a_holder(tmp_path):
    Path(lock_file(str(tmp_path))).write_text("4242\n")
    timer = _probed_for_a_moment(str(tmp_path))
    try:
        assert SessionLock.holder(str(tmp_path)) is None
    finally:
        timer.join()


_PROBER = """
import sys, time
from tellurium.session.lock import SessionLock
print(flush=True)
end = time.monotonic() + float(sys.argv[2])
while time.monotonic() < end:
    SessionLock.holder(sys.argv[1])
"""


@pytest.mark.skipif(sys.platform == "win32", reason="flock")
async def test_concurrent_probes_never_make_a_start_busy(tmp_path, fake_launch):
    """Two processes probing in a loop (MCP servers checking the name) while
    this one starts and closes the session again and again."""
    import subprocess

    from tellurium import Session

    stale = SessionLock(str(tmp_path))
    stale.acquire()  # leaves its PID behind
    stale.release()
    argv = [sys.executable, "-c", _PROBER, str(tmp_path), "3"]
    probers = [subprocess.Popen(argv, stdout=subprocess.PIPE) for _ in range(2)]
    try:
        for p in probers:
            p.stdout.readline()
        busy = 0
        for _ in range(200):
            try:
                async with Session("s", path=str(tmp_path)).start():
                    pass
            except SessionBusyError:
                busy += 1
        assert busy == 0
    finally:
        for p in probers:
            p.kill()
            p.wait()

"""SessionLock: one holder per session folder, across processes, with its PID."""

from __future__ import annotations

import os
import sys
import types

import pytest

from tellurium import SessionBusyError
from tellurium.session import SessionError
from tellurium.session.lock import LOCK_FILE, SessionLock


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
        path = tmp_path / LOCK_FILE
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


def test_acquire_creates_the_folder(tmp_path):
    lock = SessionLock(str(tmp_path / "a" / "b"))
    lock.acquire()
    lock.release()
    assert (tmp_path / "a" / "b" / LOCK_FILE).exists()


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

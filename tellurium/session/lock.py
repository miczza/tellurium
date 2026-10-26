"""SessionLock: one process at a time on a session folder.

The lock is an OS lock on ``session.lock`` inside the folder (``fcntl.flock`` on
POSIX, ``msvcrt.locking`` on Windows), held from before Chrome starts until
after it is closed; the file carries the holder's PID for the error message.
The OS drops the lock when its holder dies, ``kill -9`` included, so a
crashed process never leaves the session locked: there is nothing stale to
clean up. Every call is a non-blocking syscall on a file of a few bytes.
"""

from __future__ import annotations

import os
import sys

from tellurium.session.errors import SessionBusyError

LOCK_FILE = "session.lock"
# Windows locks byte ranges, and a locked range cannot be read by anyone
# else: lock one byte past the PID, so the PID stays readable.
_WINDOWS_OFFSET = 1 << 20


class SessionLock:
    """The lock of the session folder *path*; :meth:`acquire` and
    :meth:`release` it (closing the file also releases it)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        """Take the lock, writing our PID; :class:`SessionBusyError` if another
        holder (another process, or another lock in this one) has it."""
        if self._fd is not None:
            raise RuntimeError("session lock already held")
        os.makedirs(self.path, exist_ok=True)
        fd = os.open(self._file(), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if not _try_lock(fd):
                raise SessionBusyError(self.path, _read_pid(fd))
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, f"{os.getpid()}\n".encode())
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd

    def release(self) -> None:
        """Let the lock go; safe to call when not held."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            _unlock(fd)
        finally:
            os.close(fd)

    @staticmethod
    def holder(path: str) -> int | None:
        """The PID holding the lock of *path* (``0`` if unknown), ``None`` if it
        is free. Probes without creating anything."""
        try:
            fd = os.open(os.path.join(path, LOCK_FILE), os.O_RDWR)
        except FileNotFoundError:
            return None
        try:
            if _try_lock(fd):
                _unlock(fd)
                return None
            return _read_pid(fd) or 0
        finally:
            os.close(fd)

    def _file(self) -> str:
        return os.path.join(self.path, LOCK_FILE)


def _try_lock(fd: int) -> bool:
    """Lock *fd* without waiting; ``False`` if someone else holds it."""
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, _WINDOWS_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _unlock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, _WINDOWS_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


def _read_pid(fd: int) -> int | None:
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        return int(os.read(fd, 32).decode("ascii", "replace").strip())
    except ValueError:
        return None  # the holder has not written it yet

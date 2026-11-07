"""SessionLock: one process at a time on a session folder.

The lock is an OS lock on ``.<name>.lock`` beside the folder ``<name>``
(:func:`lock_file`; ``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows),
held from before Chrome starts until after it is closed; the file carries the
holder's PID for the error message. Beside, not inside: Windows renames no
folder with a file open in it, and a delete moves the folder away under the
lock. The name is case-folded, so ``Alice`` and ``alice`` share one lock (one
folder on Windows and macOS). A ``session.lock`` inside the folder, from
earlier versions, is ignored.
The OS drops the lock when its holder dies, ``kill -9`` included, so a
crashed process never leaves the session locked: there is nothing stale to
clean up. Every call is a non-blocking syscall on a file of a few bytes.

A probe (:meth:`SessionLock.holder`) takes the lock for an instant, shared, so
probes never see each other as holders; a start that meets one waits a moment
(:meth:`SessionLock.acquire_async`) instead of calling the session busy.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from tellurium.session.errors import SessionBusyError

# Windows locks byte ranges, and a locked range cannot be read by anyone
# else: lock one byte past the PID, so the PID stays readable.
_WINDOWS_OFFSET = 1 << 20
#: How long a start keeps trying while the lock is taken: long enough to
#: outlast a probe its process was descheduled in the middle of.
PATIENCE = 0.5
_RETRY = 0.002


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
        holder (another process, or another lock in this one) has it. Creates
        the folder's parent, not the folder."""
        if self._fd is not None:
            raise RuntimeError("session lock already held")
        file = lock_file(self.path)
        os.makedirs(os.path.dirname(file), exist_ok=True)
        fd = os.open(file, os.O_RDWR | os.O_CREAT, 0o600)
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

    async def acquire_async(self, patience: float = PATIENCE) -> None:
        """:meth:`acquire`, trying again for up to *patience* seconds while the
        lock is taken: a probe holds it for an instant and must not make the
        session look busy (with the PID of a holder long gone)."""
        deadline = time.monotonic() + patience
        while True:
            try:
                self.acquire()
                return
            except SessionBusyError:
                if time.monotonic() >= deadline:
                    raise
            await asyncio.sleep(_RETRY)

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
            fd = os.open(lock_file(path), os.O_RDWR)
        except FileNotFoundError:
            return None
        try:
            if _try_lock(fd, shared=True):
                _unlock(fd)
                return None
            return _read_pid(fd) or 0
        finally:
            os.close(fd)


def lock_file(path: str) -> str:
    """The lock file of the session folder *path*: ``.<name>.lock`` beside it,
    *name* case-folded. The parent is resolved (links, and 8.3 short names on
    Windows): the same folder by another path takes the same lock."""
    folder = os.path.normpath(os.path.abspath(path))
    parent, name = os.path.split(folder)
    return os.path.join(os.path.realpath(parent), f".{name.casefold()}.lock")


def _try_lock(fd: int, shared: bool = False) -> bool:
    """Lock *fd* without waiting; ``False`` if someone else holds it. *shared*
    (POSIX only; Windows locks are always exclusive) does not conflict with
    other shared locks, only with an exclusive one."""
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
        fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
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

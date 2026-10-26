"""Waiting for a dead holder's Chrome to let go of the session profile.

When the process holding a session dies (``kill -9`` too) the OS frees the
session lock at once, but its Chrome only notices the closed CDP pipe and exits
a moment later (~0.1 s); a Chrome started on the profile meanwhile fails with
"profile in use". Chrome marks a profile it holds with ``SingletonLock``, a
symlink to ``<hostname>-<pid>`` (POSIX). :func:`wait` polls that link until the
Chrome is gone, or reports it if it stays.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import time

#: How long a start waits for a dead holder's Chrome to exit.
TIMEOUT = 10.0
_POLL = 0.05


async def wait(chrome_dir: str, timeout: float = TIMEOUT) -> int | None:
    """Wait until no live Chrome of this host holds *chrome_dir*; ``None`` once
    free, else the PID of the Chrome still holding it after *timeout*."""
    deadline = time.monotonic() + timeout
    while True:
        pid = _holder(chrome_dir)
        if pid is None or time.monotonic() >= deadline:
            return pid
        await asyncio.sleep(_POLL)


def _holder(chrome_dir: str) -> int | None:
    """The PID of a live Chrome of this host on *chrome_dir*, from its
    ``SingletonLock``; ``None`` if there is none (or it is not ours to judge)."""
    if sys.platform == "win32":
        return None  # no SingletonLock symlink there: Chrome judges by itself
    try:
        target = os.readlink(os.path.join(chrome_dir, "SingletonLock"))
    except OSError:
        return None
    host, _, pid_text = target.rpartition("-")
    if host != socket.gethostname() or not pid_text.isdigit():
        return None  # another host's Chrome: only Chrome can tell
    pid = int(pid_text)
    if not _alive(pid):
        return None
    return pid if _runs_on(pid, chrome_dir) else None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # another user's process
    return True


def _runs_on(pid: int, chrome_dir: str) -> bool:
    """Whether *pid* was started on *chrome_dir*: a stale link may name a PID
    the system has since given to an unrelated process. Without ``/proc`` a
    live PID is taken at its word."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read()
    except FileNotFoundError:
        return not os.path.isdir("/proc")
    except OSError:
        return True  # unreadable: assume the worst, it may be Chrome
    return os.path.abspath(chrome_dir).encode() in cmdline

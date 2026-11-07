"""Waiting for a dead holder's Chrome to let go of the session profile.

When the process holding a session dies (``kill -9`` too) the OS frees the
session lock at once, but its Chrome only notices the closed CDP pipe and exits
a moment later (~0.1 s); a Chrome started on the profile meanwhile fails with
"profile in use". Chrome marks a profile it holds with ``SingletonLock``, a
symlink to ``<hostname>-<pid>`` (Linux and macOS), or on Windows with
``lockfile``, open for writing and shared for reading only while it runs.
:func:`wait` polls that mark until the Chrome is gone, or reports it if it
stays.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import time

from tellurium.session import process_args

#: How long a start waits for a dead holder's Chrome to exit.
TIMEOUT = 10.0
_POLL = 0.05
#: Whether a refused rename of the session folder is waited for: on Windows
#: the helper processes of a Chrome that let go of ``lockfile`` may still hold
#: files in it for a moment, and a folder with an open file cannot be renamed.
_MOVE_WAITS = sys.platform == "win32"


async def wait(chrome_dir: str, timeout: float = TIMEOUT) -> int | None:
    """Wait until no live Chrome of this host holds *chrome_dir*; ``None`` once
    free, else the PID of the Chrome still holding it after *timeout*."""
    deadline = time.monotonic() + timeout
    while True:
        pid = _holder(chrome_dir)
        if pid is None or time.monotonic() >= deadline:
            return pid
        await asyncio.sleep(_POLL)


async def move(src: str, dst: str, timeout: float = TIMEOUT) -> None:
    """Rename the session folder *src* to *dst* once its Chrome is gone: on
    Windows a ``PermissionError`` (a helper process of that Chrome still has
    a file open in it) is retried until *timeout*, then raised."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return await asyncio.to_thread(os.rename, src, dst)
        except PermissionError:
            if not _MOVE_WAITS or time.monotonic() >= deadline:
                raise
        await asyncio.sleep(_POLL)


def _holder(chrome_dir: str) -> int | None:
    """The PID of a live Chrome of this host on *chrome_dir*, from its
    ``SingletonLock``; ``None`` if there is none (or it is not ours to judge).
    On Windows ``0`` (the PID is not told) while its ``lockfile`` is held."""
    if sys.platform == "win32":
        return _windows_holder(chrome_dir)
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


def _windows_holder(chrome_dir: str) -> int | None:
    """``0`` while a Chrome holds *chrome_dir*'s ``lockfile``: opening it for
    writing is refused as long as Chrome has it open (it shares reading only).
    A handle of ours is closed at once: a Chrome starting meanwhile would find
    the profile in use, but nobody starts one on a profile whose session lock
    the caller holds."""
    try:
        fd = os.open(os.path.join(chrome_dir, "lockfile"), os.O_WRONLY)
    except FileNotFoundError:
        return None
    except PermissionError:
        return 0  # held (or deleted on close right now: the next poll tells)
    except OSError:
        return None
    os.close(fd)
    return None


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
    the system has since given to an unrelated process, or to a Chrome of
    another profile. Its ``--user-data-dir`` must be *chrome_dir* itself, both
    with symlinks resolved (its command line from ``/proc`` on Linux,
    ``sysctl`` on macOS). A command line the system does not tell is taken at
    its word, as is a relative value where its working directory is unknown."""
    try:
        cmdline = process_args.command_line(pid)
    except ProcessLookupError:
        return False
    if cmdline is None:
        return True  # unreadable: assume the worst, it may be Chrome
    wanted = os.path.realpath(chrome_dir)
    cwd = process_args.working_directory(pid)
    for values in _candidates(cmdline):
        if cwd is None and any(not os.path.isabs(os.fsdecode(v)) for v in values):
            return True
        paths = [os.path.join(cwd or "", os.fsdecode(v)) for v in values]
        if len(paths) > 1:  # a rewritten title: the longest that is a folder
            paths = [next((p for p in paths if os.path.isdir(p)), None)]
        if any(p is not None and os.path.realpath(p) == wanted for p in paths):
            return True
    return False


_FLAG = b"--user-data-dir="


def _candidates(cmdline: bytes) -> list[list[bytes]]:
    """For each ``--user-data-dir=`` (the only form Chrome reads) of *cmdline*
    (``/proc/<pid>/cmdline``), the values it may have, the longest first.

    Its arguments are NUL-separated, so a value is exact, unless the process
    rewrote its title, as Chrome does on Linux: then they are one string
    joined by spaces, and the value may end at any space (a path may hold
    `` --``, a URL may follow the switches) or at the end.
    """
    cmdline = cmdline.rstrip(b"\0")
    if b"\0" in cmdline:
        return [[arg[len(_FLAG) :]] for arg in cmdline.split(b"\0") if arg.startswith(_FLAG)]
    found = []
    for rest in (b" " + cmdline).split(b" " + _FLAG)[1:]:
        ends = [i for i, c in enumerate(rest) if c == ord(" ")]
        found.append([rest, *(rest[:i] for i in reversed(ends))])
    return found

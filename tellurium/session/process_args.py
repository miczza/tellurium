"""The command line of another process of this host, to tell its Chrome.

Linux reads ``/proc/<pid>/cmdline``; macOS asks the kernel with
``sysctl(KERN_PROCARGS2)`` (what ``ps`` does), through ctypes. Both give the
arguments NUL-separated, as ``/proc`` does. Every call is one syscall or a
read of a small pseudo-file: fine on the event loop.
"""

from __future__ import annotations

import os
import sys

#: An exited process not reaped yet: its arguments are gone.
ZOMBIE = b""

_CTL_KERN = 1
_KERN_ARGMAX = 8
_KERN_PROC = 14
_KERN_PROC_PID = 1
_KERN_PROCARGS2 = 49
# struct kinfo_proc of 64-bit macOS: its size, and p_stat in kp_proc.
_KINFO_PROC_SIZE = 648
_P_STAT_OFFSET = 36
_SZOMB = 5


def command_line(pid: int) -> bytes | None:
    """The NUL-separated arguments of *pid*; :data:`ZOMBIE` for a process that
    has exited (or a kernel thread), ``None`` if this system or the
    permissions do not tell. :class:`ProcessLookupError` if there is no such
    process."""
    if sys.platform == "darwin":
        return _darwin(pid)
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read()
    except FileNotFoundError:
        if os.path.isdir("/proc"):
            raise ProcessLookupError(pid) from None
        return None
    except OSError:
        return None


def working_directory(pid: int) -> str | None:
    """Where *pid*'s relative paths start, as a path to join them to; ``None``
    if this system does not tell (macOS)."""
    if sys.platform == "darwin":
        return None
    return f"/proc/{pid}/cwd"


def _sysctl(mib: list[int], size: int) -> bytes | None:
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    names = (ctypes.c_int * len(mib))(*mib)
    buffer = ctypes.create_string_buffer(size)
    length = ctypes.c_size_t(size)
    if libc.sysctl(names, len(mib), buffer, ctypes.byref(length), None, ctypes.c_size_t(0)):
        return None
    return buffer.raw[: length.value]


def _darwin(pid: int) -> bytes | None:
    info = _sysctl([_CTL_KERN, _KERN_PROC, _KERN_PROC_PID, pid], _KINFO_PROC_SIZE)
    if info is None:
        return None
    if not info:
        raise ProcessLookupError(pid)
    if len(info) == _KINFO_PROC_SIZE and info[_P_STAT_OFFSET] == _SZOMB:
        return ZOMBIE
    argmax = _sysctl([_CTL_KERN, _KERN_ARGMAX], 4)
    if argmax is None or len(argmax) != 4:
        return None
    raw = _sysctl([_CTL_KERN, _KERN_PROCARGS2, pid], int.from_bytes(argmax, sys.byteorder))
    if raw is None or len(raw) < 4:
        return None  # another user's process, or one exiting right now
    return parse_procargs2(raw)


def parse_procargs2(raw: bytes) -> bytes:
    """The arguments in a ``KERN_PROCARGS2`` buffer, NUL-separated: an ``int``
    argc, the executable's path, NUL padding, then argv (then the environment,
    left out)."""
    argc = int.from_bytes(raw[:4], sys.byteorder)
    rest = raw[4:]
    end = rest.find(b"\0")
    if end < 0:
        return b""
    rest = rest[end:].lstrip(b"\0")
    args = rest.split(b"\0")[:argc]
    return b"\0".join(args) + b"\0" if args else b""

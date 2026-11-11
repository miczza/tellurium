"""Freeze a process and thaw it, as a hung Chrome looks to tellurium.

POSIX stops it with ``SIGSTOP``; Windows suspends every thread with
``NtSuspendProcess`` (there is no signal for it).
"""

from __future__ import annotations

import os
import signal
import sys
from collections.abc import Iterator
from contextlib import contextmanager

#: ``PROCESS_SUSPEND_RESUME``: the access right NtSuspendProcess needs.
_SUSPEND_RESUME = 0x0800


@contextmanager
def frozen(pid: int) -> Iterator[None]:
    """*pid* frozen for the body of the ``with``, thawed on the way out."""
    freeze(pid)
    try:
        yield
    finally:
        thaw(pid)


def freeze(pid: int) -> None:
    if sys.platform == "win32":
        _nt("NtSuspendProcess", pid)
    else:
        os.kill(pid, signal.SIGSTOP)


def thaw(pid: int) -> None:
    if sys.platform == "win32":
        _nt("NtResumeProcess", pid)
    else:
        os.kill(pid, signal.SIGCONT)


def _nt(call: str, pid: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    function = getattr(ctypes.WinDLL("ntdll"), call)
    function.argtypes = [wintypes.HANDLE]
    function.restype = ctypes.c_long
    handle = kernel32.OpenProcess(_SUSPEND_RESUME, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        status = function(handle)
    finally:
        kernel32.CloseHandle(handle)
    if status != 0:
        raise OSError(f"{call}({pid}): NTSTATUS {status & 0xFFFFFFFF:#010x}")

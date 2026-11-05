"""Chrome on Windows: started through ``CreateProcessW`` with its CDP pipes on fds 3 and 4.

``subprocess.Popen`` cannot do it: it passes handles for fds 0-2 only, and
``STARTUPINFO.lpAttributeList["handle_list"]`` makes a handle *inheritable*
without giving it an fd number in the child. Chrome's
``--remote-debugging-pipe`` reads ``_get_osfhandle(3)`` and writes
``_get_osfhandle(4)``, i.e. it needs *CRT file descriptors* 3 and 4. The only
mechanism that fills a child's CRT fd table is the block the MSVC runtime reads
from ``STARTUPINFO.lpReserved2`` (the one libuv and Node write).

The child gets exactly the handles listed in ``PROC_THREAD_ATTRIBUTE_HANDLE_LIST``
(its two pipe ends and its standard handles), whatever else is inheritable in
the parent at that moment; its environment is a Unicode block of ours, and its
standard output and error go where the caller says (``STARTF_USESTDHANDLES``).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping

# Flags from the MSVC CRT (internal/ioinit.cpp): a handle entry is only
# adopted when FOPEN is set; FPIPE tells the CRT the handle is a pipe.
_CRT_FOPEN = 0x01
_CRT_FPIPE = 0x08

#: ``INVALID_HANDLE_VALUE`` — the placeholder for an fd slot the child must
#: resolve itself (the CRT falls back to ``GetStdHandle`` for fds 0/1/2).
_INVALID_HANDLE_VALUE = -1

_STARTF_USESTDHANDLES = 0x00000100
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
_WAIT_OBJECT_0 = 0
_INFINITE = 0xFFFFFFFF


def build_crt_inherit_block(handles: list[int | None], handle_size: int = 8) -> bytes:
    """Encode the MSVC CRT ``STARTUPINFO.lpReserved2`` inheritance block.

    Its layout is::

        int   count;               // number of fd slots
        char  flags[count];        // per-fd CRT flags
        HANDLE osfhnd[count];      // per-fd OS handle (pointer-sized)

    *handles* is indexed by file descriptor; ``None`` marks an unused slot.
    *handle_size* is the child's pointer size (8 on win64, 4 on win32).
    """
    count = len(handles)
    flags = bytearray()
    raw = bytearray()
    mask = (1 << (handle_size * 8)) - 1
    for handle in handles:
        if handle is None:
            flags.append(0)
            raw += (_INVALID_HANDLE_VALUE & mask).to_bytes(handle_size, "little")
        else:
            flags.append(_CRT_FOPEN | _CRT_FPIPE)
            raw += (handle & mask).to_bytes(handle_size, "little")
    return count.to_bytes(4, "little") + bytes(flags) + bytes(raw)


def build_environment_block(env: Mapping[str, str]) -> str:
    """The ``lpEnvironment`` of ``CreateProcessW`` (with ``CREATE_UNICODE_ENVIRONMENT``):
    ``NAME=value`` strings, each ``\\0``-terminated, sorted by name without regard to
    case as Windows keeps them, and one more ``\\0`` at the end. Names that differ
    only in case are one variable on Windows: the last one given wins.

    :class:`ValueError` for a name that is empty, holds ``=`` past its first
    character (``=C:`` is how Windows names a drive's current directory) or a NUL,
    and for a value holding a NUL.
    """
    entries: dict[str, str] = {}
    for name, value in env.items():
        if not name or "=" in name[1:] or "\0" in name:
            raise ValueError(f"invalid environment variable name: {name!r}")
        if "\0" in value:
            raise ValueError(f"environment variable {name!r} holds a NUL character")
        entries[name.upper()] = f"{name}={value}\0"  # one entry per name: the last wins
    return "".join(entries[key] for key in sorted(entries)) + "\0"


def launch_chrome_windows(
    chrome_path: str,
    args: list[str],
    output: int = subprocess.DEVNULL,
    env: Mapping[str, str] | None = None,
) -> tuple[WindowsProcess, int, int]:
    """Start Chrome with its CDP pipes on fds 3 (Chrome reads) and 4 (Chrome writes).

    Chrome's standard output and error go to *output* (an fd of ours, or
    ``subprocess.DEVNULL``), its input is ``NUL``. *env*, when given, is its
    whole environment (``None`` inherits ours).

    Returns ``(process, parent_write_fd, parent_read_fd)``: the parent ends as
    CRT fds, ready for :class:`~tellurium.cdp.transport._pipe_win.PipeWindowsTransport`.
    """
    if sys.platform != "win32":
        raise RuntimeError("launch_chrome_windows() is Windows-only; use process.launch_chrome().")
    import _winapi
    import msvcrt

    environment = build_environment_block(env) if env is not None else None
    chrome_read_h, parent_write_h = _winapi.CreatePipe(None, 0)
    parent_read_h, chrome_write_h = _winapi.CreatePipe(None, 0)
    owned = [chrome_read_h, parent_write_h, parent_read_h, chrome_write_h]
    devnull_fds: list[int] = []
    lent: list[int] = []  # handles of ours made inheritable for the child only
    try:
        for handle in (parent_write_h, parent_read_h):
            os.set_handle_inheritable(handle, False)
        if output == subprocess.DEVNULL:
            devnull_fds.append(os.open(os.devnull, os.O_WRONLY))
            output = devnull_fds[-1]
        devnull_fds.append(os.open(os.devnull, os.O_RDONLY))
        stdin_h = msvcrt.get_osfhandle(devnull_fds[-1])
        output_h = msvcrt.get_osfhandle(output)
        for handle in (stdin_h, output_h):
            if not os.get_handle_inheritable(handle):
                os.set_handle_inheritable(handle, True)
                lent.append(handle)
        for handle in (chrome_read_h, chrome_write_h):
            os.set_handle_inheritable(handle, True)
        handle_pid = _create_process(
            chrome_path,
            subprocess.list2cmdline([chrome_path, *args]),
            environment,
            stdio=(stdin_h, output_h, output_h),
            crt_fds=[None, None, None, chrome_read_h, chrome_write_h],
        )
    except BaseException:
        for handle in owned:
            _winapi.CloseHandle(handle)
        raise
    finally:
        for handle in lent:
            os.set_handle_inheritable(handle, False)
        for fd in devnull_fds:
            os.close(fd)
    # The child has its own ends now.
    _winapi.CloseHandle(chrome_read_h)
    _winapi.CloseHandle(chrome_write_h)
    # The fds own the parent's handles from here on.
    # Binary: a text-mode fd would turn \n into \r\n and stop reading at a 0x1A.
    parent_write_fd = msvcrt.open_osfhandle(parent_write_h, os.O_BINARY)
    parent_read_fd = msvcrt.open_osfhandle(parent_read_h, os.O_RDONLY | os.O_BINARY)
    return WindowsProcess(*handle_pid), parent_write_fd, parent_read_fd


def _create_process(
    application: str,
    command_line: str,
    environment: str | None,
    *,
    stdio: tuple[int, int, int],
    crt_fds: list[int | None],
) -> tuple[int, int]:
    """``CreateProcessW`` with the CRT block, the standard handles and a handle
    list of exactly those; returns ``(process handle, pid)``."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.c_void_p),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    kernel32.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel32.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
    kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    kernel32.DeleteProcThreadAttributeList.restype = None
    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    kernel32.CreateProcessW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    def wide(text: str) -> ctypes.Array:
        """A writable UTF-16 copy of *text*, NUL-terminated (surrogate pairs kept)."""
        return ctypes.create_string_buffer(text.encode("utf-16-le") + b"\0\0")

    def fail(what: str) -> OSError:
        code = ctypes.get_last_error()
        return OSError(code, f"{what} failed for {application}: {ctypes.FormatError(code)}")

    block = build_crt_inherit_block(crt_fds, handle_size=ctypes.sizeof(ctypes.c_void_p))
    reserved = ctypes.create_string_buffer(block, len(block))
    # Each handle once: the handle list refuses duplicates.
    inherited = list(dict.fromkeys([*stdio, *(h for h in crt_fds if h is not None)]))
    handles = (wintypes.HANDLE * len(inherited))(*inherited)

    size = ctypes.c_size_t()
    kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    attributes = ctypes.create_string_buffer(size.value)
    if not kernel32.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)):
        raise fail("InitializeProcThreadAttributeList")
    try:
        if not kernel32.UpdateProcThreadAttribute(
            attributes,
            0,
            _PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
            handles,
            ctypes.sizeof(handles),
            None,
            None,
        ):
            raise fail("UpdateProcThreadAttribute")
        startup = STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        startup.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput, startup.StartupInfo.hStdOutput = stdio[0], stdio[1]
        startup.StartupInfo.hStdError = stdio[2]
        startup.StartupInfo.cbReserved2 = len(block)
        startup.StartupInfo.lpReserved2 = ctypes.cast(reserved, ctypes.c_void_p)
        startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
        env_buffer = wide(environment) if environment else None
        info = PROCESS_INFORMATION()
        if not kernel32.CreateProcessW(
            application,
            wide(command_line),
            None,  # process security attributes
            None,  # thread security attributes
            True,  # bInheritHandles: limited to the handle list
            _EXTENDED_STARTUPINFO_PRESENT | _CREATE_UNICODE_ENVIRONMENT,
            env_buffer,
            None,  # current directory: ours
            ctypes.byref(startup),
            ctypes.byref(info),
        ):
            raise fail("CreateProcessW")
    finally:
        kernel32.DeleteProcThreadAttributeList(attributes)
    kernel32.CloseHandle(info.hThread)
    return info.hProcess, info.dwProcessId


class WindowsProcess:
    """The part of ``subprocess.Popen`` the launch uses, around a process handle.

    :meth:`terminate` and :meth:`kill` both end the process at once
    (``TerminateProcess``): Windows has no polite signal for a GUI process.
    The handle is closed once the exit code is known, so the pid can no
    longer name another process here.
    """

    def __init__(self, handle: int, pid: int) -> None:
        self._handle: int | None = handle
        self.pid = pid
        self.returncode: int | None = None

    def _reap(self, timeout_ms: int) -> int | None:
        import _winapi

        if self.returncode is None and self._handle is not None:
            if _winapi.WaitForSingleObject(self._handle, timeout_ms) == _WAIT_OBJECT_0:
                self.returncode = _winapi.GetExitCodeProcess(self._handle)
                _winapi.CloseHandle(self._handle)
                self._handle = None
        return self.returncode

    def poll(self) -> int | None:
        return self._reap(0)

    def wait(self, timeout: float | None = None) -> int:
        ms = _INFINITE if timeout is None else max(0, int(timeout * 1000))
        code = self._reap(ms)
        if code is None:
            raise subprocess.TimeoutExpired("chrome", timeout)
        return code

    def terminate(self) -> None:
        import _winapi

        if self.poll() is None and self._handle is not None:
            try:
                _winapi.TerminateProcess(self._handle, 1)
            except PermissionError:  # already exiting: the wait tells
                pass

    kill = terminate

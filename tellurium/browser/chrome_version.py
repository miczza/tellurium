"""Chrome's version, read from the executable without opening a browser window.

Linux and macOS ask the executable (``--version``); macOS falls back to the
bundle's ``Info.plist`` when the flag prints nothing. Windows never runs the
executable: ``chrome.exe --version`` opens a window and does not exit. There
the version is the name of the directory next to the executable (the
installer's layout), else the file's ``VERSIONINFO`` resource.

Every source touches the disk or starts a process: callers on the event loop
run :func:`detect_chrome_version` through ``asyncio.to_thread``.
"""

from __future__ import annotations

import plistlib
import re
import struct
import subprocess
import sys
from pathlib import Path

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)\.(\d+)")

#: Seconds ``--version`` may take; a cold start of a large binary is slow.
VERSION_FLAG_TIMEOUT = 10.0

#: ``VS_FIXEDFILEINFO.dwSignature``.
_FIXED_INFO_SIGNATURE = 0xFEEF04BD


def detect_chrome_version(executable: str) -> tuple[int, ...] | None:
    """The four parts of *executable*'s version, or None when no source tells it."""
    if sys.platform == "win32":
        return _from_install_layout(executable) or _from_version_resource(executable)
    found = _from_version_flag(executable)
    if found is None and sys.platform == "darwin":
        found = _from_bundle_plist(executable)
    return found


def _parse(text: str, *, whole: bool = False) -> tuple[int, ...] | None:
    match = _VERSION_RE.fullmatch(text) if whole else _VERSION_RE.search(text)
    return tuple(int(x) for x in match.groups()) if match else None


def _from_version_flag(executable: str) -> tuple[int, ...] | None:
    try:
        output = subprocess.check_output(
            [executable, "--version"],
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=VERSION_FLAG_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return _parse(output.decode(errors="replace"))


def _from_bundle_plist(executable: str) -> tuple[int, ...] | None:
    """``CFBundleShortVersionString`` of the ``.app`` holding *executable*
    (``<name>.app/Contents/MacOS/<name>``)."""
    contents = Path(executable).parent.parent
    if Path(executable).parent.name != "MacOS" or contents.name != "Contents":
        return None
    try:
        with open(contents / "Info.plist", "rb") as plist:
            info = plistlib.load(plist)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
    version = info.get("CFBundleShortVersionString") if isinstance(info, dict) else None
    return _parse(version, whole=True) if isinstance(version, str) else None


def _from_install_layout(executable: str) -> tuple[int, ...] | None:
    """The highest ``<a>.<b>.<c>.<d>`` directory next to *executable*: Chrome's
    installer keeps the version's files there (one more during an update)."""
    try:
        entries = list(Path(executable).parent.iterdir())
    except OSError:
        return None
    versions = [v for e in entries if e.is_dir() and (v := _parse(e.name, whole=True))]
    return max(versions, default=None)


def _version_from_fixed_info(raw: bytes) -> tuple[int, ...] | None:
    """The file version in a ``VS_FIXEDFILEINFO`` (signature, struct version,
    then the version's most and least significant DWORDs)."""
    if len(raw) < 16:
        return None
    signature, _struct_version, ms, ls = struct.unpack_from("<4I", raw)
    if signature != _FIXED_INFO_SIGNATURE or not (ms or ls):
        return None
    return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)


def _from_version_resource(executable: str) -> tuple[int, ...] | None:
    """The ``VERSIONINFO`` resource of *executable*, through ``version.dll``."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    try:
        api = ctypes.WinDLL("version", use_last_error=True)
    except OSError:
        return None
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    api.GetFileVersionInfoW.restype = wintypes.BOOL
    api.VerQueryValueW.argtypes = [
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.UINT),
    ]
    api.VerQueryValueW.restype = wintypes.BOOL

    size = api.GetFileVersionInfoSizeW(executable, None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(executable, 0, size, data):
        return None
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not api.VerQueryValueW(data, "\\", ctypes.byref(pointer), ctypes.byref(length)):
        return None
    if not pointer.value or not length.value:
        return None
    return _version_from_fixed_info(ctypes.string_at(pointer.value, length.value))

"""Single source of truth for the patched-browser cache layout.

Layout (shared by ``PatchedEngine``, the CLI and the download tooling)::

    ~/.tellurium/chromium/                      <- cache_root()
        146.0.7680.188/                         <- one dir per chromium_upstream
            chrome                              <- binary (BINARY_NAME)
            MANIFEST.json                       <- release manifest (optional)
            chrome_sandbox, *.pak, locales/ ... <- runtime resources
        current -> 146.0.7680.188               <- symlink to the default version
    ~/.tellurium/.update-check                  <- daily update-check cache

Directory names are the *chromium upstream version* (e.g. ``146.0.7680.188``),
which is also the value accepted by ``Browser.launch(chromium_version=...)`` and
persisted by ``Session``.  The directory content is the extracted release
tarball of chromium-telluride (top-level ``chromium-telluride/`` stripped).

Override the root with the ``TELLURIUM_CACHE_DIR`` environment variable.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import shutil
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BINARY_NAME = "chrome.exe" if sys.platform == "win32" else "chrome"
#: Legacy name used by tellurium <= 0.1.0 docs; still accepted when found.
_LEGACY_BINARY_NAME = "tellurium-chromium"
CURRENT_LINK = "current"
LOCK_NAME = ".install.lock"
#: Taken by an install before the lock itself and held until it ends, and by a
#: reader for an instant around taking the lock shared: while an install waits,
#: no new reader gets in, so readers taking turns cannot starve it.
GATE_NAME = ".install.gate"
#: An install moved aside during a swap; one outside the lock is an orphan.
OLD_PREFIX = ".old-"
MANIFEST_NAME = "MANIFEST.json"
#: How long a launch waits for an install in progress to release the cache.
LOCK_TIMEOUT = 60.0
_LOCK_POLL = 0.05


class LockWaitStopped(RuntimeError):
    """Raised when the caller's stop event ends a wait for the install lock."""


_VERSION_RE = re.compile(r"\d+(?:\.\d+){3}")


def checked_version(version: str) -> str:
    """Return *version* if it is a chromium version (``146.0.7680.188``).

    Version names become directory names under the cache root, and some come
    from downloaded manifests: anything else (``../..``, an absolute path)
    could point outside the cache. Raises ValueError.
    """
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise ValueError(f"Not a chromium version: {version!r} (expected e.g. 146.0.7680.188)")
    return version


def tellurium_home() -> Path:
    """Return ``~/.tellurium`` (or ``$TELLURIUM_CACHE_DIR``)."""
    override = os.environ.get("TELLURIUM_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".tellurium"


def cache_root() -> Path:
    """Return the patched-browser cache root (``~/.tellurium/chromium``)."""
    return tellurium_home() / "chromium"


def update_check_file(root: Path | None = None) -> Path:
    root = root if root is not None else cache_root()
    return root.parent / ".update-check"


def binary_in(version_dir: Path) -> Path | None:
    """Return the browser binary inside *version_dir*, or None if absent."""
    for name in (BINARY_NAME, _LEGACY_BINARY_NAME):
        candidate = version_dir / name
        if candidate.is_file():
            return candidate
    return None


def binary_sha256(binary: Path, *, trust_record: bool = True) -> str:
    """SHA256 of *binary*, remembered beside it until the file changes.

    Hashing the ~300 MB binary on every launch costs seconds. The record
    (``.<name>.sha256``) is keyed on size, inode, mtime and change time:
    rewriting the file, or putting its mtime back afterwards, updates the
    change time and forces a new hash. An unreadable or unwritable record,
    or a change time that cannot be read, just means hashing.

    Trust boundary: the record lives in the version directory, next to the
    binary and its MANIFEST.json. Whoever can replace the binary can also
    rewrite both, so the record is good enough for the MANIFEST check and
    nothing stronger. A hash the caller brings from outside (a
    ``chromium_sha256`` pin) must use ``trust_record=False``: the file is
    hashed in full and the record only refreshed.
    """
    from tellurium.browser import _manifest

    st = binary.stat()
    try:
        key: list[int] | None = [st.st_size, st.st_ino, st.st_mtime_ns, _change_time_ns(binary, st)]
    except OSError:
        key = None  # no change time: never trust the record
    record = binary.with_name(f".{binary.name}.sha256")
    try:
        cached = json.loads(record.read_text())
        if trust_record and key is not None and cached["stat"] == key:
            return str(cached["sha256"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    digest = _manifest._sha256_file(binary)
    try:
        record.write_text(json.dumps({"stat": key, "sha256": digest}))
    except OSError:
        pass
    return digest


def _change_time_ns(path: Path, st: os.stat_result) -> int:
    """When the data or metadata of *path* last changed, in ns.

    ``st_ctime`` on POSIX. On Windows ``st_ctime`` is the creation time, which
    a rewrite in place leaves alone: there it is ``ChangeTime`` of the file's
    ``FILE_BASIC_INFO``. OSError when it cannot be read.
    """
    if sys.platform != "win32":
        return st.st_ctime_ns
    import ctypes
    from ctypes import wintypes

    class BasicInfo(ctypes.Structure):
        _fields_ = [(n, ctypes.c_int64) for n in ("created", "accessed", "written", "changed")]
        _fields_ += [("attributes", wintypes.DWORD)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
    k32.CreateFileW.argtypes += [wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID]
    k32.GetFileInformationByHandleEx.argtypes += [wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    # FILE_READ_ATTRIBUTES, shared for read, write and delete, OPEN_EXISTING
    handle = k32.CreateFileW(str(path), 0x80, 0x7, None, 3, 0, None)
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = BasicInfo()
        if not k32.GetFileInformationByHandleEx(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())  # 0 is FileBasicInfo
        return int(info.changed) * 100
    finally:
        k32.CloseHandle(handle)


@dataclass(frozen=True)
class InstalledBrowser:
    version: str
    path: Path  # version directory
    binary: Path
    manifest: dict[str, Any] | None
    is_current: bool

    @property
    def expected_sha256(self) -> str | None:
        """SHA256 of the binary declared by MANIFEST.json for this platform."""
        if not self.manifest:
            return None
        from tellurium.browser._manifest import current_platform

        table = self.manifest.get("binary_sha256")
        if isinstance(table, dict):
            return table.get(current_platform())
        return None


def _version_key(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def current_version(root: Path | None = None) -> str | None:
    """Return the version the ``current`` symlink points to, or None."""
    root = root if root is not None else cache_root()
    link = root / CURRENT_LINK
    if link.is_symlink():
        try:
            return link.resolve().name
        except OSError:
            return None
    return None


@contextlib.contextmanager
def install_lock(root: Path | None = None) -> Iterator[None]:
    """Hold the cache's install lock: one install or ``current`` switch at a time.

    Excludes other processes and other threads (each holder opens its own
    descriptor). POSIX uses ``fcntl.flock``; Windows ``msvcrt.locking`` on the
    lock file's first byte, retried until it is free. The gate
    (:data:`GATE_NAME`) is taken first and kept: readers already in finish,
    new ones wait for this install.
    """
    root = root if root is not None else cache_root()
    root.mkdir(parents=True, exist_ok=True)
    with _exclusive(root / GATE_NAME), _exclusive(root / LOCK_NAME):
        yield


@contextlib.contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    """*path* locked exclusive, waiting as long as it takes."""
    with open(path, "a+b") as fh:
        if sys.platform == "win32":
            import msvcrt

            while True:
                fh.seek(0)
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:  # LK_LOCK gives up after ~10 s: keep waiting
                    continue
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def reading_lock(root: Path, stop: threading.Event | None = None) -> Iterator[None]:
    """Hold the install lock *shared* while reading the cache.

    Installs, which hold it exclusive, are waited for (at most
    :data:`LOCK_TIMEOUT`, then :class:`TimeoutError`; setting *stop* ends the
    wait with :class:`LockWaitStopped`); other readers are not (POSIX;
    Windows has no shared lock, there readers exclude each other too), but
    no reader enters while an install waits (see :data:`GATE_NAME`). A
    lock file that cannot be opened for permissions (a read-only mount, an
    image, another user's cache) means reading without the lock: this
    process could not install there either.
    """
    fh = _open_lock(root / LOCK_NAME)
    if fh is None:
        yield
        return
    gate = _open_lock(root / GATE_NAME)  # None: a cache no install can write
    with fh, gate if gate is not None else contextlib.nullcontext():
        _acquire(fh, gate, root, stop)
        try:
            yield
        finally:
            _unlock(fh)


def _try_lock(fh: Any) -> None:
    """Take the lock on *fh* without waiting (shared on POSIX); OSError if held."""
    if sys.platform == "win32":
        import msvcrt

        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)


def _unlock(fh: Any) -> None:
    if sys.platform == "win32":
        import msvcrt

        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _try_gate(fh: Any) -> None:
    """Take the gate on *fh* exclusive without waiting; OSError if held."""
    if sys.platform == "win32":
        import msvcrt

        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _acquire(fh: Any, gate: Any, root: Path, stop: threading.Event | None) -> None:
    """Take the lock on *fh*, passing through *gate* (if any) for the
    instant it takes; give up when *stop* is set or after :data:`LOCK_TIMEOUT`."""
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        if _try(_try_gate, gate):
            try:
                if _try(_try_lock, fh):
                    return
            finally:
                if gate is not None:
                    _unlock(gate)
        if stop is not None and stop.is_set():
            raise LockWaitStopped(f"Stopped waiting for the install lock of {root}")
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"The patched-browser cache {root} has been held by another install for "
                f"over {LOCK_TIMEOUT:.0f} s (its install lock): is a "
                "`tellurium download-browser` suspended or stuck?"
            )
        if stop is not None:
            stop.wait(_LOCK_POLL)
        else:
            time.sleep(_LOCK_POLL)


def _try(take: Any, fh: Any) -> bool:
    """``take(fh)``: True if taken (or *fh* is None), False if held by someone else."""
    if fh is None:
        return True
    try:
        take(fh)
        return True
    except BlockingIOError:  # POSIX: held by an install
        return False
    except OSError:
        # msvcrt reports a held lock as PermissionError; on POSIX any other
        # error (no flock on this filesystem) is not worth waiting for.
        if sys.platform != "win32":
            raise
        return False


def _open_lock(path: Path) -> Any:
    """The lock file opened for locking, or ``None`` if permissions forbid it."""
    modes = ("a+b",) if sys.platform == "win32" else ("a+b", "rb")
    for mode in modes:
        try:
            return open(path, mode)  # noqa: SIM115 - the caller closes it
        except (PermissionError, FileNotFoundError):
            continue
        except OSError as e:
            if e.errno != errno.EROFS:
                raise
    return None


def remove_orphans(root: Path | None = None) -> list[Path]:
    """Delete the moved-aside installs an interrupted swap left (under the lock)."""
    root = root if root is not None else cache_root()
    if not root.is_dir():
        return []
    with install_lock(root):
        return sweep_orphans(root)


def sweep_orphans(root: Path) -> list[Path]:
    """:func:`remove_orphans` for a caller already holding :func:`install_lock`."""
    orphans = sorted(p for p in root.glob(f"{OLD_PREFIX}*") if p.is_dir())
    for path in orphans:
        shutil.rmtree(path, ignore_errors=True)
    return orphans


def remove_installed(path: Path) -> None:
    """Delete an installed version directory under the install lock."""
    with install_lock(path.parent):
        shutil.rmtree(path)


def set_current(version: str, root: Path | None = None) -> Path:
    """Point the ``current`` symlink at *version* (atomic replace, under the install lock)."""
    root = root if root is not None else cache_root()
    with install_lock(root):
        return point_current(version, root)


def point_current(version: str, root: Path) -> Path:
    """:func:`set_current` for a caller already holding :func:`install_lock`."""
    target = root / checked_version(version)
    link = root / CURRENT_LINK
    tmp = root / f".{CURRENT_LINK}.{uuid.uuid4().hex}.tmp"
    tmp.symlink_to(target.name, target_is_directory=True)
    try:
        _move_link_in(tmp, link)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return link


def _move_link_in(new: Path, link: Path) -> None:
    """Rename the link *new* to *link*, replacing it.

    One rename where the system allows it. Windows refuses to rename over a
    directory, and a directory link is one (``ERROR_ACCESS_DENIED``): the old
    link moves aside first and goes after; if the new one cannot move in, the
    old one comes back. Engines read the link under :func:`reading_lock`,
    which waits for the install lock this caller holds.
    """
    try:
        os.replace(new, link)
        return
    except PermissionError:
        if not link.is_symlink():
            raise
    aside = link.with_name(f".{link.name}.{uuid.uuid4().hex}.old")
    os.replace(link, aside)
    try:
        os.replace(new, link)
    except BaseException:
        os.replace(aside, link)
        raise
    with contextlib.suppress(OSError):
        aside.unlink()


def installed_browsers(root: Path | None = None) -> list[InstalledBrowser]:
    """Scan the cache root; newest version first."""
    root = root if root is not None else cache_root()
    if not root.is_dir():
        return []
    cur = current_version(root)
    found: list[InstalledBrowser] = []
    for d in root.iterdir():
        if d.name == CURRENT_LINK or d.name.startswith(".") or not d.is_dir():
            continue
        binary = binary_in(d)
        if binary is None:
            continue
        manifest: dict[str, Any] | None = None
        mpath = d / MANIFEST_NAME
        if mpath.is_file():
            try:
                manifest = json.loads(mpath.read_text())
            except (OSError, ValueError):
                manifest = None
        found.append(
            InstalledBrowser(
                version=d.name,
                path=d,
                binary=binary,
                manifest=manifest,
                is_current=(d.name == cur),
            )
        )
    found.sort(key=lambda b: _version_key(b.version), reverse=True)
    return found


def installed_version(root: Path | None = None) -> str | None:
    """Return the default installed version (``current`` or newest)."""
    cur = current_version(root)
    if cur:
        return cur
    browsers = installed_browsers(root)
    return browsers[0].version if browsers else None

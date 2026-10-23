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
import json
import os
import re
import shutil
import sys
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
#: An install moved aside during a swap; one outside the lock is an orphan.
OLD_PREFIX = ".old-"
MANIFEST_NAME = "MANIFEST.json"


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
    (``.<name>.sha256``) is keyed on size, inode, mtime and ctime: rewriting
    the file, or putting its mtime back afterwards, updates the ctime and
    forces a new hash. An unreadable or unwritable record just means hashing.

    Trust boundary: the record lives in the version directory, next to the
    binary and its MANIFEST.json. Whoever can replace the binary can also
    rewrite both, so the record is good enough for the MANIFEST check and
    nothing stronger. A hash the caller brings from outside (a
    ``chromium_sha256`` pin) must use ``trust_record=False``: the file is
    hashed in full and the record only refreshed.
    """
    from tellurium.browser import _manifest

    st = binary.stat()
    key = [st.st_size, st.st_ino, st.st_mtime_ns, st.st_ctime_ns]
    record = binary.with_name(f".{binary.name}.sha256")
    try:
        cached = json.loads(record.read_text())
        if trust_record and cached["stat"] == key:
            return str(cached["sha256"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    digest = _manifest._sha256_file(binary)
    try:
        record.write_text(json.dumps({"stat": key, "sha256": digest}))
    except OSError:
        pass
    return digest


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
    lock file's first byte, retried until it is free.
    """
    root = root if root is not None else cache_root()
    root.mkdir(parents=True, exist_ok=True)
    with open(root / LOCK_NAME, "a+b") as fh:
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
        os.replace(tmp, link)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return link


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

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

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BINARY_NAME = "chrome.exe" if sys.platform == "win32" else "chrome"
#: Legacy name used by tellurium <= 0.1.0 docs; still accepted when found.
_LEGACY_BINARY_NAME = "tellurium-chromium"
CURRENT_LINK = "current"
MANIFEST_NAME = "MANIFEST.json"


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


@dataclass(frozen=True)
class InstalledBrowser:
    version: str
    path: Path            # version directory
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


def set_current(version: str, root: Path | None = None) -> Path:
    """Point the ``current`` symlink at *version* (atomic replace)."""
    root = root if root is not None else cache_root()
    target = root / version
    link = root / CURRENT_LINK
    tmp = root / f".{CURRENT_LINK}.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(target.name, target_is_directory=True)
    os.replace(tmp, link)
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
        found.append(InstalledBrowser(
            version=d.name, path=d, binary=binary, manifest=manifest,
            is_current=(d.name == cur),
        ))
    found.sort(key=lambda b: _version_key(b.version), reverse=True)
    return found


def installed_version(root: Path | None = None) -> str | None:
    """Return the default installed version (``current`` or newest)."""
    cur = current_version(root)
    if cur:
        return cur
    browsers = installed_browsers(root)
    return browsers[0].version if browsers else None

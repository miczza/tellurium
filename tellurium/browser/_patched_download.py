"""Download and install chromium-telluride release tarballs.

Release contract (``chromium-telluride/docs/manifest-schema.md``):

* tag ``v<telluride_version>-<chromium_upstream>``
* assets ``chromium-telluride-<chromium_upstream>-<platform>.tar.gz``,
  ``MANIFEST.json`` and ``SHA256SUMS``
* tarball top-level directory ``chromium-telluride/`` containing ``chrome``,
  ``MANIFEST.json`` and the runtime resources.

Installation target: ``<cache_root>/<chromium_upstream>/`` (see ``_cache``).
Zero third-party dependencies: ``urllib`` + ``tarfile`` only.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tellurium.browser import _cache
from tellurium.browser._manifest import (
    ReleaseManifest,
    _sha256_file,
    current_platform,
    verify_binary,
)

log = logging.getLogger("tellurium")

GITHUB_REPO = "miczza/chromium-telluride"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
_USER_AGENT = "tellurium (+https://github.com/miczza/tellurium)"
_TOP_DIR = "chromium-telluride"

ProgressCallback = Callable[[int, int | None], None]


class DownloadError(RuntimeError):
    """Raised when a release cannot be found, fetched, or verified."""


@dataclass(frozen=True)
class ReleaseAssets:
    tag: str
    tarball_url: str
    tarball_name: str
    manifest_url: str | None
    sha256sums_url: str | None


# --------------------------------------------------------------------------- #
# GitHub API
# --------------------------------------------------------------------------- #


def _http_json(url: str, timeout: float = 15) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read())


def _http_text(url: str, timeout: float = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _assets_from_release(rel: dict[str, Any], platform: str) -> ReleaseAssets | None:
    suffix = f"-{platform}.tar.gz"
    tarball = manifest = sums = None
    tarball_name = ""
    for a in rel.get("assets", []):
        name = a.get("name", "")
        url = a.get("browser_download_url")
        if name.startswith("chromium-telluride-") and name.endswith(suffix):
            tarball, tarball_name = url, name
        elif name == "MANIFEST.json":
            manifest = url
        elif name == "SHA256SUMS":
            sums = url
    if not tarball:
        return None
    return ReleaseAssets(
        tag=rel.get("tag_name", ""),
        tarball_url=tarball,
        tarball_name=tarball_name,
        manifest_url=manifest,
        sha256sums_url=sums,
    )


def find_release(
    version: str | None = None, *, platform: str | None = None, api_url: str = RELEASES_API
) -> ReleaseAssets:
    """Locate release assets for *version* (chromium upstream) or the latest."""
    platform = platform or current_platform()
    if version is None:
        rel = _http_json(f"{api_url}/latest")
        assets = _assets_from_release(rel, platform)
        if assets is None:
            raise DownloadError(
                f"Latest release {rel.get('tag_name')} has no {platform} tarball asset."
            )
        return assets
    releases = _http_json(f"{api_url}?per_page=50")
    for rel in releases:
        tag = rel.get("tag_name", "")
        if tag.endswith(f"-{version}") or tag == version or tag == f"v{version}":
            assets = _assets_from_release(rel, platform)
            if assets is None:
                raise DownloadError(f"Release {tag} has no {platform} tarball asset.")
            return assets
    raise DownloadError(
        f"No chromium-telluride release found for version {version} "
        f"(checked {len(releases)} most recent releases at {api_url})."
    )


def latest_version(*, api_url: str = RELEASES_API) -> str | None:
    """Return the chromium upstream version of the latest release, or None."""
    try:
        rel = _http_json(f"{api_url}/latest")
    except Exception as e:  # noqa: BLE001
        log.debug("latest_version failed: %s", e)
        return None
    tag = str(rel.get("tag_name", "")).lstrip("v")
    # v0.1.0-146.0.7680.188 -> 146.0.7680.188 ; 146.0.7680.188 -> itself
    return tag.rsplit("-", 1)[-1] if tag else None


# --------------------------------------------------------------------------- #
# Download + verify + extract
# --------------------------------------------------------------------------- #


def _download(url: str, dest: Path, progress: ProgressCallback | None = None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:  # noqa: S310
        total_hdr = resp.headers.get("Content-Length")
        total = int(total_hdr) if total_hdr and total_hdr.isdigit() else None
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)


def _expected_tarball_sha(sums_text: str, tarball_name: str) -> str | None:
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == tarball_name:
            return parts[0].lower()
    return None


def _checked(version: str, context: str = "Invalid version") -> str:
    try:
        return _cache.checked_version(version)
    except ValueError as e:
        raise DownloadError(f"{context}: {e}") from None


def _release_tarball_sha(assets: ReleaseAssets) -> str | None:
    """The tarball's SHA256 from the release's SHA256SUMS, or None if unavailable."""
    if not assets.sha256sums_url:
        return None
    try:
        return _expected_tarball_sha(_http_text(assets.sha256sums_url), assets.tarball_name)
    except Exception as e:  # noqa: BLE001 — any failure means "not verified"
        log.warning("Could not fetch SHA256SUMS: %s", e)
        return None


def _safe_extract(tar_path: Path, dest: Path) -> None:
    """Extract *tar_path* into *dest*, stripping the ``chromium-telluride/`` top dir."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tf:
        members = []
        for m in tf.getmembers():
            name = m.name
            if name.startswith(f"{_TOP_DIR}/"):
                name = name[len(_TOP_DIR) + 1 :]
            elif name == _TOP_DIR:
                continue
            if not name:
                continue
            p = Path(name)
            if p.is_absolute() or ".." in p.parts:
                raise DownloadError(f"Refusing to extract unsafe path {m.name!r}")
            if m.islnk():
                # A hardlink names its target by archive path: strip the same
                # top dir, or tarfile cannot find it after the rename.
                if not m.linkname.startswith(f"{_TOP_DIR}/"):
                    raise DownloadError(f"Refusing to extract unsafe link {m.name!r}")
                m.linkname = m.linkname[len(_TOP_DIR) + 1 :]
            if m.issym() or m.islnk():
                target = Path(m.linkname)
                if target.is_absolute() or ".." in target.parts:
                    raise DownloadError(f"Refusing to extract unsafe link {m.name!r}")
            m.name = name
            members.append(m)
        try:
            tf.extractall(dest, members=members, filter="data")
        except TypeError:  # Python < 3.12 without the filter backport
            tf.extractall(dest, members=members)  # noqa: S202


def install_from_tarball(
    tar_path: Path,
    *,
    cache_root: Path | None = None,
    expected_tarball_sha256: str | None = None,
    set_current: bool = True,
    force: bool = False,
) -> _cache.InstalledBrowser:
    """Install a local release tarball into the cache and return the entry.

    The swap into place and the ``current`` switch run under the cache's
    install lock; an install of the same binary that is already there is
    kept (Chrome may be running from it) unless *force*. Filesystem errors
    are raised as :class:`DownloadError`.
    """
    try:
        return _install(tar_path, cache_root, expected_tarball_sha256, set_current, force)
    except OSError as e:
        raise DownloadError(f"Could not install chromium-telluride: {e}") from e


def _install(
    tar_path: Path,
    cache_root: Path | None,
    expected_tarball_sha256: str | None,
    set_current: bool,
    force: bool,
) -> _cache.InstalledBrowser:
    root = cache_root if cache_root is not None else _cache.cache_root()
    root.mkdir(parents=True, exist_ok=True)
    if expected_tarball_sha256:
        actual = _sha256_file(tar_path)
        if actual != expected_tarball_sha256.lower():
            raise DownloadError(
                f"Tarball SHA256 mismatch: expected {expected_tarball_sha256}, got {actual}"
            )

    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=root))
    try:
        _safe_extract(tar_path, staging)
        manifest_path = staging / _cache.MANIFEST_NAME
        if not manifest_path.is_file():
            raise DownloadError("Tarball has no MANIFEST.json; refusing to install.")
        manifest = ReleaseManifest.from_path(manifest_path)
        binary = _cache.binary_in(staging)
        if binary is None:
            raise DownloadError(f"Tarball has no {_cache.BINARY_NAME} binary.")
        binary.chmod(binary.stat().st_mode | 0o111)  # before hashing: chmod changes ctime
        verify_binary(binary, manifest, current_platform())
        sandbox = staging / "chrome_sandbox"
        if sandbox.is_file():
            sandbox.chmod(sandbox.stat().st_mode | 0o111)

        version = manifest.install_dir_name
        final = root / _checked(version, "Refusing install dir from MANIFEST.json")
        if final.resolve().parent != root.resolve():
            raise DownloadError(f"Refusing install dir outside the cache: {final}")
        with _cache.install_lock(root):
            _cache.sweep_orphans(root)
            _swap_in(staging, final, manifest, force)
            if set_current or _cache.current_version(root) is None:
                if sys.platform != "win32":
                    _cache.point_current(version, root)
            # Read under the lock: another install may swap the directory next.
            entry = {b.version: b for b in _cache.installed_browsers(root)}.get(version)
    finally:
        shutil.rmtree(staging, ignore_errors=True)  # gone already once swapped in
    if entry is None:
        raise DownloadError(f"chromium-telluride {version} is not in the cache after installing")
    log.info("chromium-telluride %s installed at %s", version, final)
    return entry


def _swap_in(staging: Path, final: Path, manifest: ReleaseManifest, force: bool) -> None:
    """Move *staging* to *final*; the caller holds the install lock."""
    present = _cache.binary_in(final) if final.is_dir() else None
    expected = manifest.binary_sha256.get(current_platform())
    if not force and present is not None and _cache.binary_sha256(present) == expected:
        log.info("chromium-telluride %s already installed; kept", final.name)
        return
    if not (final.exists() or final.is_symlink()):
        staging.rename(final)
        return
    old = final.with_name(f"{_cache.OLD_PREFIX}{final.name}-{uuid.uuid4().hex}")
    final.rename(old)  # never a moment with a half-deleted install in place
    try:
        staging.rename(final)
    except BaseException:
        old.rename(final)  # the previous install goes back where it was
        raise
    shutil.rmtree(old, ignore_errors=True)


def download_patched(
    version: str | None = None,
    *,
    cache_root: Path | None = None,
    progress: ProgressCallback | None = None,
    api_url: str = RELEASES_API,
    set_current: bool = True,
    allow_unverified: bool = False,
    force: bool = False,
) -> _cache.InstalledBrowser:
    """Download and install a chromium-telluride release (latest by default).

    The tarball must match the release's ``SHA256SUMS``: the MANIFEST that
    checks the binary ships inside the same tarball, so it proves nothing
    alone. A missing or unreadable ``SHA256SUMS`` is a :class:`DownloadError`
    unless *allow_unverified* is set.
    """
    if version is not None:
        _checked(version)
    assets = find_release(version, api_url=api_url)
    expected = _release_tarball_sha(assets)
    if expected is None and not allow_unverified:
        raise DownloadError(
            f"Release {assets.tag}: no SHA256SUMS entry for {assets.tarball_name}; "
            "refusing an unverified download (allow_unverified=True to override)."
        )
    root = cache_root if cache_root is not None else _cache.cache_root()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=root) as tmp:
        tar_path = Path(tmp) / assets.tarball_name
        log.info("Downloading %s (%s)", assets.tarball_name, assets.tag)
        _download(assets.tarball_url, tar_path, progress)
        return install_from_tarball(
            tar_path,
            cache_root=root,
            expected_tarball_sha256=expected,
            set_current=set_current,
            force=force,
        )


def reinstall(
    version: str,
    *,
    cache_root: Path | None = None,
    progress: ProgressCallback | None = None,
    api_url: str = RELEASES_API,
    allow_unverified: bool = False,
) -> _cache.InstalledBrowser:
    """Download *version* again and swap it in place of the installed copy.

    The installed copy is replaced only once the new one is downloaded and
    verified: a failed reinstall leaves it as it was.
    """
    root = cache_root if cache_root is not None else _cache.cache_root()
    _checked(version)
    return download_patched(
        version,
        cache_root=root,
        progress=progress,
        api_url=api_url,
        set_current=_cache.current_version(root) == version,
        allow_unverified=allow_unverified,
        force=True,
    )

"""Browser engine abstraction — stock Chrome vs patched Chromium."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import threading
from abc import ABC, abstractmethod
from pathlib import Path

from tellurium.browser import _cache, _update_check

logger = logging.getLogger("tellurium")

#: How long a cancelled launch waits for the binary resolution to stop: a
#: download stops at its next chunk, the update check within its timeout.
STOP_TIMEOUT = 10.0


class BinaryCorruptedError(RuntimeError):
    """Raised when binary SHA256 does not match expected (MANIFEST or pin)."""


class BrowserEngine(ABC):
    @abstractmethod
    async def get_executable(self) -> str: ...
    @abstractmethod
    def build_args(self, profile: object | None) -> list[str]: ...
    @abstractmethod
    def capabilities(self) -> set[str]: ...


class StockEngine(BrowserEngine):
    def __init__(self, executable: str | None = None):
        self._executable = executable

    async def get_executable(self) -> str:
        from tellurium.browser.launcher import find_chrome

        if self._executable:
            return self._executable
        return await find_chrome()

    def build_args(self, profile: object | None) -> list[str]:
        return []

    def capabilities(self) -> set[str]:
        return set()


class PatchedEngine(BrowserEngine):
    """chromium-telluride backend.

    Binary resolution order: explicit ``executable`` > pinned
    ``chromium_version`` in the cache > ``current`` symlink in the cache
    (with a silent daily update check).  Cache layout: see ``_cache``.

    Flags emitted (contract: ``chromium-telluride/docs/usage.md``):
    ``--fingerprint=<seed>`` (always; random seed when no profile/seed is
    given because the fork requires it), ``--fingerprint-platform=<os>``
    and ``--fingerprint-webrtc-ip=<mode>``.
    """

    VERSION = "146.0.7680.188"

    def __init__(
        self,
        *,
        executable: str | None = None,
        cache_root: Path | None = None,
        chromium_version: str | None = None,
        chromium_sha256: str | None = None,
        auto_security_update: bool = False,
        webrtc_ip_flag: str | None = None,
        seed: int | None = None,
    ):
        self._executable = executable
        self._cache_root = cache_root or _cache.cache_root()
        self._chromium_version = chromium_version
        self._chromium_sha256 = chromium_sha256
        self._auto_security_update = auto_security_update
        self._webrtc_ip_flag = webrtc_ip_flag
        self._seed = seed
        if auto_security_update and chromium_version:
            logger.warning(
                "auto_security_update=True is ignored when chromium_version is pinned "
                "(%s); unpin or run `tellurium update-browser --security-only`.",
                chromium_version,
            )

    @property
    def seed(self) -> int | None:
        """Fingerprint seed passed to the binary (set after ``build_args``)."""
        return self._seed

    # ------------------------------------------------------------------ #
    # Binary resolution
    # ------------------------------------------------------------------ #

    def _maybe_auto_security_update(self, stop: threading.Event | None = None) -> None:
        info = _update_check.check_for_update(cache_root=self._cache_root)
        if info is None or not info.security or not self._auto_security_update:
            return
        from tellurium.browser._patched_download import (
            DownloadCancelled,
            DownloadError,
            download_patched,
        )

        logger.warning(
            "auto_security_update: installing security release %s (CVE: %s)",
            info.latest,
            ", ".join(info.manifest.get("cve", [])) or "n/a",
        )
        if stop is not None and stop.is_set():
            raise DownloadCancelled("auto_security_update cancelled")
        try:
            download_patched(info.latest, cache_root=self._cache_root, stop=stop)
        except DownloadCancelled:
            raise
        except DownloadError as e:
            logger.error("auto_security_update failed: %s", e)

    def resolve_binary_path(self, stop: threading.Event | None = None) -> Path:
        """Find and verify the binary to launch (blocking: run it in a thread).

        Setting *stop* from another thread ends a security download in flight
        (:class:`~tellurium.browser._patched_download.DownloadCancelled`).
        The cache is read under its install lock (shared), so a reinstall
        swapping the version directory is waited for instead of seen half
        done; a cache this process may not lock is read without it.
        """
        if not self._chromium_version:
            self._maybe_auto_security_update(stop)
        root = self._cache_root
        lock = _cache.reading_lock(root, stop) if root.is_dir() else contextlib.nullcontext()
        with lock:
            return self._find_binary()

    def _find_binary(self) -> Path:
        if self._chromium_version:
            version_dir = self._cache_root / self._chromium_version
        else:
            current = _cache.current_version(self._cache_root)
            if current is None:
                # No symlink yet: fall back to the newest installed version.
                browsers = _cache.installed_browsers(self._cache_root)
                current = browsers[0].version if browsers else None
            version_dir = self._cache_root / (current or _cache.CURRENT_LINK)
        binary = _cache.binary_in(version_dir)
        if binary is None:
            hint = f" --version {self._chromium_version}" if self._chromium_version else ""
            raise FileNotFoundError(
                f"chromium-telluride binary not found in {version_dir}. "
                f"Run `tellurium download-browser --browser patched{hint}` "
                f"or pass executable=/path/to/chrome."
            )
        if self._chromium_sha256:
            # A pin comes from outside the cache: never taken from the record.
            actual = _cache.binary_sha256(binary, trust_record=False)
            if actual != self._chromium_sha256:
                raise BinaryCorruptedError(
                    f"SHA256 mismatch for {binary}: expected {self._chromium_sha256}, "
                    f"got {actual}. Run `tellurium verify-browser --reinstall`."
                )
        manifest_path = version_dir / _cache.MANIFEST_NAME
        if manifest_path.exists():
            from tellurium.browser._manifest import ReleaseManifest, current_platform, verify_binary

            manifest = ReleaseManifest.from_path(manifest_path)
            verify_binary(binary, manifest, current_platform())
        else:
            logger.warning(
                "No MANIFEST.json in %s; skipping integrity verification. "
                "Reinstall with `tellurium download-browser --browser patched` "
                "to get a verified manifest.",
                version_dir,
            )
        return binary

    async def get_executable(self) -> str:
        if self._executable:
            return self._executable
        # In a thread: the daily update check (HTTP), a security download and
        # the binary hash all block. A cancellation stops the thread too, and
        # waits for it: no download goes on, no partial file stays behind.
        stop = threading.Event()
        work = asyncio.ensure_future(asyncio.to_thread(self.resolve_binary_path, stop))
        try:
            return str(await asyncio.shield(work))
        except asyncio.CancelledError:
            stop.set()
            await asyncio.wait([work], timeout=STOP_TIMEOUT)
            raise
        finally:
            # Retrieved here, so a failure after a cancellation is not reported as lost.
            work.add_done_callback(lambda done: done.cancelled() or done.exception())

    # ------------------------------------------------------------------ #
    # Flags
    # ------------------------------------------------------------------ #

    def build_args(self, profile: object | None) -> list[str]:
        seed = getattr(profile, "seed", None)
        if seed is None:
            seed = self._seed
        if seed is None:
            # The fork requires --fingerprint; never launch un-fingerprinted.
            seed = secrets.randbits(31)
            logger.info("No seed given for patched engine; using random seed %d", seed)
        self._seed = int(seed)
        args = [f"--fingerprint={self._seed}"]
        target_os = getattr(profile, "target_os", None)
        if target_os:
            args.append(f"--fingerprint-platform={target_os}")
        if self._webrtc_ip_flag is not None:
            args.append(f"--fingerprint-webrtc-ip={self._webrtc_ip_flag}")
        return args

    def capabilities(self) -> set[str]:
        return {
            "native_fingerprint",
            "native_client_hints",
            "native_cdp_fix",
            "native_network_timing",
            "native_navigator",
        }


def select_engine(
    browser: str,
    executable: str | None,
    *,
    chromium_version: str | None,
    chromium_sha256: str | None,
    auto_security_update: bool,
    webrtc_ip_flag: str | None,
) -> BrowserEngine:
    """The engine ``Browser.launch(browser=...)`` asks for: ``"patched"`` or stock.

    The patched-only options are ignored, with a warning, for a stock browser.
    """
    if browser == "patched":
        return PatchedEngine(
            executable=executable,
            chromium_version=chromium_version,
            chromium_sha256=chromium_sha256,
            auto_security_update=auto_security_update,
            webrtc_ip_flag=webrtc_ip_flag,
        )
    if chromium_version or chromium_sha256 or auto_security_update:
        logger.warning(
            "chromium_version/chromium_sha256/auto_security_update are only "
            "meaningful with browser='patched'; ignoring for browser=%r.",
            browser,
        )
    return StockEngine(executable=executable)

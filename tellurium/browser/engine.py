"""Browser engine abstraction — stock Chrome vs patched Chromium."""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from tellurium.browser import _update_check
from tellurium.browser._manifest import _sha256_file


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
    VERSION = "146.0.7680.188"

    def __init__(
        self,
        *,
        executable: str | None = None,
        cache_root: Path | None = None,
        chromium_version: str | None = None,
        chromium_sha256: str | None = None,
        auto_security_update: bool = False,
    ):
        self._executable = executable
        self._cache_root = cache_root or (Path.home() / ".tellurium" / "chromium")
        self._chromium_version = chromium_version
        self._chromium_sha256 = chromium_sha256
        self._auto_security_update = auto_security_update

    def resolve_binary_path(self) -> Path:
        if self._chromium_version:
            version_dir = self._cache_root / self._chromium_version
        else:
            # Use 'current' symlink and trigger daily update check
            _update_check.check_for_update(cache_root=self._cache_root)
            version_dir = self._cache_root / "current"
        binary = version_dir / "tellurium-chromium"
        if not binary.exists():
            raise FileNotFoundError(
                f"tellurium-chromium binary not found at {binary}. "
                f"Run `tellurium download-browser --browser patched`"
                + (f" --version {self._chromium_version}" if self._chromium_version else "")
            )
        if self._chromium_sha256:
            actual = _sha256_file(binary)
            if actual != self._chromium_sha256:
                raise BinaryCorruptedError(
                    f"SHA256 mismatch for {binary}: expected {self._chromium_sha256}, "
                    f"got {actual}. Run `tellurium verify-browser --reinstall`."
                )
        manifest_path = version_dir / "MANIFEST.json"
        if manifest_path.exists():
            from tellurium.browser._manifest import ReleaseManifest, verify_binary, current_platform
            manifest = ReleaseManifest.from_path(manifest_path)
            verify_binary(binary, manifest, current_platform())
        else:
            logger = logging.getLogger("tellurium")
            logger.warning(
                "No MANIFEST.json in %s; skipping integrity verification. "
                "Reinstall with `tellurium download-browser` to get a signed manifest.",
                version_dir,
            )
        return binary

    async def get_executable(self) -> str:
        # Preserve existing behavior: explicit executable wins
        if self._executable:
            return self._executable
        # New behavior: use resolve_binary_path (pinned or default-via-update-check)
        return str(self.resolve_binary_path())

    def build_args(self, profile: object | None) -> list[str]:
        if profile is None:
            return []
        args = [f"--fingerprint={profile.seed}"]
        if getattr(profile, "target_os", None):
            args.append(f"--fingerprint-platform={profile.target_os}")
        if getattr(profile, "timezone", None):
            args.append(f"--fingerprint-timezone={profile.timezone}")
        if getattr(profile, "locale", None):
            args.append(f"--fingerprint-locale={profile.locale}")
        return args

    def capabilities(self) -> set[str]:
        return {"native_fingerprint", "native_client_hints", "native_cdp_fix",
                "native_network_timing", "native_navigator"}

"""Browser engine abstraction — stock Chrome vs patched Chromium."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path


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

    def __init__(self, executable: str | None = None):
        self._executable = executable

    async def get_executable(self) -> str:
        if self._executable:
            return self._executable
        path = Path.home() / ".tellurium" / f"chromium-patched-{self.VERSION}" / "chrome"
        if not path.exists():
            raise FileNotFoundError(
                f"tellurium-chromium {self.VERSION} not found. "
                f"Download with: tellurium download-browser --browser patched"
            )
        return str(path)

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

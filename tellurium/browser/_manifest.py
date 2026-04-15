"""Read and verify tellurium-chromium release manifests."""
from __future__ import annotations
import hashlib
import json
import platform as _plat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    """Return hex SHA256 of *path*. Task 4 may switch to chunked hashing."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_platform() -> str:
    """Return the MANIFEST.json platform key for the current host.

    Format is {os}-{arch}: linux-x64, linux-arm64, mac-x64, mac-arm64, win-x64.
    Differs from CfT's _determine_platform() which uses 'linux64' style.
    """
    machine = _plat.machine().lower()
    if sys.platform.startswith("linux"):
        return "linux-arm64" if machine in ("aarch64", "arm64") else "linux-x64"
    if sys.platform == "darwin":
        return "mac-arm64" if machine in ("arm64", "aarch64") else "mac-x64"
    if sys.platform == "win32":
        return "win-x64"
    return "linux-x64"  # fallback


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    previous: str
    security: bool
    cve: list[str]
    severity: str
    released_at: str
    chromium_upstream: str
    data_version: str
    binary_sha256: dict[str, str]

    @classmethod
    def from_path(cls, path: Path) -> ReleaseManifest:
        data: dict[str, Any] = json.loads(path.read_text())
        return cls(
            version=data["version"],
            previous=data.get("previous", ""),
            security=bool(data.get("security", False)),
            cve=list(data.get("cve", [])),
            severity=data.get("severity", "none"),
            released_at=data.get("released_at", ""),
            chromium_upstream=data.get("chromium_upstream", ""),
            data_version=data.get("data_version", ""),
            binary_sha256=dict(data["binary_sha256"]),
        )


def verify_binary(binary_path: Path, manifest: ReleaseManifest, platform: str) -> None:
    """Raise BinaryCorruptedError if SHA256 of binary does not match manifest."""
    from tellurium.browser.engine import BinaryCorruptedError
    expected = manifest.binary_sha256.get(platform)
    if not expected:
        raise BinaryCorruptedError(
            f"No SHA256 for platform {platform} in manifest {manifest.version}"
        )
    actual = _sha256_file(binary_path)
    if actual != expected:
        raise BinaryCorruptedError(
            f"SHA256 mismatch for {binary_path}: expected {expected}, got {actual}. "
            f"Run `tellurium verify-browser --reinstall`."
        )

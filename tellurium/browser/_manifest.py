"""Read and verify tellurium-chromium release manifests."""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
            binary_sha256=dict(data.get("binary_sha256", {})),
        )


def verify_binary(binary_path: Path, manifest: ReleaseManifest, platform: str) -> None:
    """Raise BinaryCorruptedError if SHA256 of binary does not match manifest."""
    from tellurium.browser.engine import BinaryCorruptedError
    expected = manifest.binary_sha256.get(platform)
    if not expected:
        raise BinaryCorruptedError(
            f"No SHA256 for platform {platform} in manifest {manifest.version}"
        )
    actual = hashlib.sha256(binary_path.read_bytes()).hexdigest()
    if actual != expected:
        raise BinaryCorruptedError(
            f"SHA256 mismatch for {binary_path}: expected {expected}, got {actual}. "
            f"Run `tellurium verify-browser --reinstall`."
        )

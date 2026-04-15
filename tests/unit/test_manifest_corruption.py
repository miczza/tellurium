import hashlib
import json
import pytest
from pathlib import Path
from tellurium.browser._manifest import ReleaseManifest, verify_binary
from tellurium.browser.engine import BinaryCorruptedError


def _make_manifest(binary_bytes: bytes, platform: str = "linux-x64") -> dict:
    return {
        "version": "146.0.7680.188",
        "previous": "146.0.7680.180",
        "security": False,
        "cve": [],
        "severity": "none",
        "released_at": "2026-04-15T00:00:00Z",
        "chromium_upstream": "146.0.7680.188",
        "data_version": "2026-04",
        "binary_sha256": {platform: hashlib.sha256(binary_bytes).hexdigest()},
    }


def test_manifest_verify_happy_path(tmp_path):
    bin_bytes = b"chromium-binary-content"
    binary = tmp_path / "tellurium-chromium"
    binary.write_bytes(bin_bytes)
    manifest_path = tmp_path / "MANIFEST.json"
    manifest_path.write_text(json.dumps(_make_manifest(bin_bytes)))

    m = ReleaseManifest.from_path(manifest_path)
    verify_binary(binary, m, "linux-x64")


def test_manifest_verify_mismatch_raises(tmp_path):
    bin_bytes = b"chromium-binary-content"
    binary = tmp_path / "tellurium-chromium"
    binary.write_bytes(bin_bytes)
    manifest_path = tmp_path / "MANIFEST.json"
    manifest_path.write_text(json.dumps(_make_manifest(b"different-content")))

    m = ReleaseManifest.from_path(manifest_path)
    with pytest.raises(BinaryCorruptedError, match="SHA256 mismatch"):
        verify_binary(binary, m, "linux-x64")


def test_manifest_verify_missing_platform_raises(tmp_path):
    bin_bytes = b"chromium-binary-content"
    binary = tmp_path / "tellurium-chromium"
    binary.write_bytes(bin_bytes)
    manifest_path = tmp_path / "MANIFEST.json"
    manifest_path.write_text(json.dumps(_make_manifest(bin_bytes, "windows-x64")))

    m = ReleaseManifest.from_path(manifest_path)
    with pytest.raises(BinaryCorruptedError, match="No SHA256 for platform"):
        verify_binary(binary, m, "linux-x64")


def test_manifest_missing_binary_sha256_raises_keyerror(tmp_path):
    """A manifest without binary_sha256 at all must fail at parse time."""
    manifest_path = tmp_path / "MANIFEST.json"
    manifest_path.write_text(json.dumps({
        "version": "146.0.7680.188",
        # binary_sha256 intentionally missing
    }))
    with pytest.raises(KeyError, match="binary_sha256"):
        ReleaseManifest.from_path(manifest_path)

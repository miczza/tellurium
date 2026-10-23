"""The binary's SHA256 is remembered until the file changes (audit m12)."""

from __future__ import annotations

import hashlib
import json
import os
import time

import pytest

from tellurium.browser import _cache, _manifest


def _counting(monkeypatch) -> list:
    calls: list = []
    real = _manifest._sha256_file

    def spy(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(_manifest, "_sha256_file", spy)
    return calls


def test_second_lookup_does_not_rehash(tmp_path, monkeypatch):
    binary = tmp_path / "chrome"
    binary.write_bytes(b"binary v1")
    calls = _counting(monkeypatch)
    expected = hashlib.sha256(b"binary v1").hexdigest()
    assert _cache.binary_sha256(binary) == expected
    assert _cache.binary_sha256(binary) == expected
    assert len(calls) == 1


def test_a_changed_binary_is_hashed_again(tmp_path, monkeypatch):
    binary = tmp_path / "chrome"
    binary.write_bytes(b"binary v1")
    calls = _counting(monkeypatch)
    _cache.binary_sha256(binary)
    st = binary.stat()
    time.sleep(0.05)  # past the filesystem's timestamp granularity
    binary.write_bytes(b"binary v2")  # same size
    os.utime(binary, ns=(st.st_atime_ns, st.st_mtime_ns))  # mtime put back
    assert _cache.binary_sha256(binary) == hashlib.sha256(b"binary v2").hexdigest()
    assert len(calls) == 2


def test_a_corrupt_or_unwritable_record_falls_back_to_hashing(tmp_path, monkeypatch):
    binary = tmp_path / "chrome"
    binary.write_bytes(b"binary")
    _cache.binary_sha256(binary)
    record = next(p for p in tmp_path.iterdir() if p.name != "chrome")
    record.write_text("{not json")
    assert _cache.binary_sha256(binary) == hashlib.sha256(b"binary").hexdigest()
    record.unlink()
    record.mkdir()  # cannot be written: still answers
    assert _cache.binary_sha256(binary) == hashlib.sha256(b"binary").hexdigest()


def test_the_record_is_not_listed_as_a_browser(tmp_path):
    version = tmp_path / "146.0.7680.188"
    version.mkdir()
    (version / _cache.BINARY_NAME).write_bytes(b"x")
    _cache.binary_sha256(version / _cache.BINARY_NAME)
    assert [b.version for b in _cache.installed_browsers(tmp_path)] == ["146.0.7680.188"]


# --- wired into verification and the engine ---------------------------------


def _install(tmp_path, content: bytes = b"binary-content"):
    from tellurium.browser._manifest import current_platform

    root = tmp_path / "chromium"
    version = root / "146.0.7680.188"
    version.mkdir(parents=True)
    (version / _cache.BINARY_NAME).write_bytes(content)
    manifest = {
        "version": "0.1.0",
        "chromium_upstream": "146.0.7680.188",
        "binary_sha256": {current_platform(): hashlib.sha256(content).hexdigest()},
    }
    (version / _cache.MANIFEST_NAME).write_text(json.dumps(manifest))
    return root, version / _cache.BINARY_NAME


def test_verify_binary_hashes_once_per_file_version(tmp_path, monkeypatch):
    from tellurium.browser._manifest import ReleaseManifest, current_platform, verify_binary

    root, binary = _install(tmp_path)
    manifest = ReleaseManifest.from_path(binary.with_name(_cache.MANIFEST_NAME))
    calls = _counting(monkeypatch)
    verify_binary(binary, manifest, current_platform())
    verify_binary(binary, manifest, current_platform())
    assert len(calls) == 1


def test_engine_launches_reuse_the_hash_for_the_manifest(tmp_path, monkeypatch):
    from tellurium.browser.engine import PatchedEngine

    root, binary = _install(tmp_path)
    calls = _counting(monkeypatch)
    for _ in range(3):
        engine = PatchedEngine(cache_root=root, chromium_version="146.0.7680.188")
        assert engine.resolve_binary_path() == binary
    assert len(calls) == 1


def test_a_pin_is_always_checked_against_a_full_hash(tmp_path, monkeypatch):
    from tellurium.browser.engine import PatchedEngine

    root, binary = _install(tmp_path)
    pin = hashlib.sha256(b"binary-content").hexdigest()
    calls = _counting(monkeypatch)
    for _ in range(3):
        engine = PatchedEngine(
            cache_root=root, chromium_version="146.0.7680.188", chromium_sha256=pin
        )
        assert engine.resolve_binary_path() == binary
    assert len(calls) == 3  # one full hash per launch; the MANIFEST check reuses it


def test_a_forged_record_does_not_defeat_the_pin(tmp_path):
    from tellurium.browser.engine import BinaryCorruptedError, PatchedEngine

    root, binary = _install(tmp_path)
    pin = hashlib.sha256(b"binary-content").hexdigest()
    time.sleep(0.05)
    binary.write_bytes(b"evil-content!!")
    st = binary.stat()
    record = binary.with_name(f".{binary.name}.sha256")
    key = [st.st_size, st.st_ino, st.st_mtime_ns, st.st_ctime_ns]
    record.write_text(json.dumps({"stat": key, "sha256": pin}))
    engine = PatchedEngine(cache_root=root, chromium_version="146.0.7680.188", chromium_sha256=pin)
    with pytest.raises(BinaryCorruptedError, match="SHA256 mismatch"):
        engine.resolve_binary_path()


def test_a_tampered_binary_still_fails_verification(tmp_path, monkeypatch):
    from tellurium.browser.engine import BinaryCorruptedError, PatchedEngine

    root, binary = _install(tmp_path)
    engine = PatchedEngine(cache_root=root, chromium_version="146.0.7680.188")
    engine.resolve_binary_path()
    time.sleep(0.05)
    binary.write_bytes(b"binary-c0ntent")  # same size
    with pytest.raises(BinaryCorruptedError):
        engine.resolve_binary_path()


async def test_engine_get_executable_does_not_block_the_loop(tmp_path, monkeypatch):
    import asyncio

    from tellurium.browser.engine import PatchedEngine

    def slow_resolve(self):
        time.sleep(0.6)
        return tmp_path / "chrome"

    monkeypatch.setattr(PatchedEngine, "resolve_binary_path", slow_resolve)
    gaps: list[float] = []

    async def ticker() -> None:
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.01)
            gaps.append(time.monotonic() - last)
            last = time.monotonic()

    tick = asyncio.create_task(ticker())
    try:
        assert await PatchedEngine(cache_root=tmp_path).get_executable() == str(tmp_path / "chrome")
    finally:
        tick.cancel()
    assert gaps and max(gaps) < 0.3, f"event loop blocked for {max(gaps or [0]):.2f}s"

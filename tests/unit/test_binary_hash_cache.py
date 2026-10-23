"""The binary's SHA256 is remembered until the file changes (audit m12)."""

from __future__ import annotations

import hashlib
import os
import time

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

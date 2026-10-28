"""Resolving the patched binary: a cancelled launch stops the download it
started and leaves ``current`` alone; a forced reinstall in flight does not
make a concurrent launch miss the binary."""

from __future__ import annotations

import asyncio
import shutil
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from tellurium.browser import _cache
from tellurium.browser import _patched_download as dl
from tellurium.browser.engine import PatchedEngine

OLD = "145.0.7600.1"
NEW = "146.0.7680.188"


def _install(root, version):
    version_dir = root / version
    version_dir.mkdir(parents=True)
    (version_dir / "chrome").write_bytes(b"binary " + version.encode())
    return version_dir


class _EndlessTarball:
    """A response that trickles chunks until the test ends (3 s at most: the
    event loop waits for its threads before closing)."""

    def __init__(self, abort: threading.Event) -> None:
        self.headers = {"Content-Length": str(1 << 40)}
        self.reads = 0
        self.started = threading.Event()
        self._abort = abort

    def read(self, n=-1):
        if self._abort.is_set() or self.reads >= 300:
            return b""
        time.sleep(0.01)
        self.reads += 1
        if self.reads >= 3:
            self.started.set()
        return b"x" * 4096

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None


@pytest.fixture
def security_release(tmp_path, monkeypatch):
    """A cache on OLD, a security release NEW announced, its tarball endless."""
    root = tmp_path / "cache"
    _install(root, OLD)
    _cache.set_current(OLD, root)
    abort = threading.Event()
    response = _EndlessTarball(abort)
    info = SimpleNamespace(security=True, latest=NEW, manifest={"cve": []})
    monkeypatch.setattr("tellurium.browser._update_check.check_for_update", lambda **kw: info)
    assets = dl.ReleaseAssets(
        "v0.1.0-" + NEW, "https://example.invalid/t.tar.gz", "t.tar.gz", None, None
    )
    monkeypatch.setattr(dl, "find_release", lambda version=None, **kw: assets)
    monkeypatch.setattr(dl, "_release_tarball_sha", lambda assets: "ab" * 32)
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: response)
    yield root, response
    abort.set()


async def test_cancelling_the_launch_stops_the_download(security_release):
    root, response = security_release
    engine = PatchedEngine(cache_root=root, auto_security_update=True)
    resolving = asyncio.ensure_future(engine.get_executable())
    assert await asyncio.to_thread(response.started.wait, 10), "the download never started"

    resolving.cancel()
    with pytest.raises(asyncio.CancelledError):
        await resolving

    reads = response.reads
    await asyncio.sleep(0.2)
    assert response.reads == reads, "the download goes on after the cancellation"
    assert _cache.current_version(root) == OLD
    leftovers = [p.name for p in root.iterdir() if p.name.startswith((".download-", ".install-"))]
    assert leftovers == []


def test_a_forced_reinstall_in_flight_does_not_hide_the_binary(tmp_path, monkeypatch):
    monkeypatch.setattr("tellurium.browser._update_check.check_for_update", lambda **kw: None)
    root = tmp_path / "cache"
    _install(root, NEW)
    _cache.set_current(NEW, root)
    moved_aside = threading.Event()

    def reinstall() -> None:  # what _swap_in does, slowed down
        final = root / NEW
        with _cache.install_lock(root):
            old = final.with_name(f"{_cache.OLD_PREFIX}{NEW}")
            final.rename(old)
            moved_aside.set()
            time.sleep(0.3)
            _install(root, NEW)
            shutil.rmtree(old)

    swapper = threading.Thread(target=reinstall)
    swapper.start()
    try:
        assert moved_aside.wait(5)
        binary = PatchedEngine(cache_root=root).resolve_binary_path()
    finally:
        swapper.join(5)
    assert binary.is_file()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
@pytest.mark.parametrize("lock_file", ["absent", "read-only"])
def test_a_read_only_cache_still_launches(tmp_path, monkeypatch, lock_file):
    """A cache nobody can reinstall into (ro mount, image, another user's) is read without lock."""
    monkeypatch.setattr("tellurium.browser._update_check.check_for_update", lambda **kw: None)
    root = tmp_path / "cache"
    version_dir = _install(root, NEW)
    _cache.set_current(NEW, root)
    lock = root / _cache.LOCK_NAME
    if lock_file == "absent":
        lock.unlink()
    else:
        lock.chmod(0o444)
    root.chmod(0o555)
    try:
        binary = PatchedEngine(cache_root=root).resolve_binary_path()
    finally:
        root.chmod(0o755)
    assert binary.is_file() and binary.resolve().parent == version_dir


def _held_lock(root):
    """A thread holding the install lock (a `download-browser` suspended with Ctrl-Z)."""
    held, release = threading.Event(), threading.Event()

    def hold() -> None:
        with _cache.install_lock(root):
            held.set()
            release.wait(30)

    holder = threading.Thread(target=hold)
    holder.start()
    assert held.wait(5)
    return holder, release


def test_waiting_for_a_held_lock_has_a_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("tellurium.browser._update_check.check_for_update", lambda **kw: None)
    monkeypatch.setattr(_cache, "LOCK_TIMEOUT", 0.3)
    root = tmp_path / "cache"
    _install(root, NEW)
    _cache.set_current(NEW, root)
    holder, release = _held_lock(root)
    try:
        with pytest.raises(TimeoutError, match="install lock"):
            PatchedEngine(cache_root=root).resolve_binary_path()
    finally:
        release.set()
        holder.join(5)


async def test_cancelling_the_launch_stops_waiting_for_the_lock(tmp_path, monkeypatch):
    monkeypatch.setattr("tellurium.browser._update_check.check_for_update", lambda **kw: None)
    root = tmp_path / "cache"
    _install(root, NEW)
    _cache.set_current(NEW, root)
    holder, release = _held_lock(root)
    try:
        resolving = asyncio.ensure_future(PatchedEngine(cache_root=root).get_executable())
        await asyncio.sleep(0.2)
        loop = asyncio.get_running_loop()
        start = loop.time()
        resolving.cancel()
        with pytest.raises(asyncio.CancelledError):
            await resolving
        assert loop.time() - start < 1.0, "the resolving thread kept waiting for the lock"
    finally:
        release.set()
        holder.join(5)

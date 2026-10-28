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
from tellurium.browser.engine import STOP_TIMEOUT, PatchedEngine
from tests.unit.test_patched_download import _fake_github, _make_tarball

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
    monkeypatch.setattr(dl, "_release_tarball_sha", lambda assets, timeout=15: "ab" * 32)
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


def _stopping_github(tmp_path, stop, when):
    """The fake GitHub of test_patched_download, setting *stop* when *when* is fetched."""
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    urlopen, calls, name = _fake_github(tmp_path, tar)
    timeouts: list[float | None] = []

    def stopping(req, timeout=None):
        timeouts.append(timeout)
        reply = urlopen(req, timeout)
        if when in calls[-1]:
            stop.set()
        return reply

    return stopping, calls, name, timeouts


@pytest.mark.parametrize("when", ["/releases", "SHA256SUMS"])
def test_a_stop_while_finding_the_release_downloads_nothing(tmp_path, monkeypatch, when):
    stop = threading.Event()
    urlopen, calls, name, _ = _stopping_github(tmp_path, stop, when)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    root = tmp_path / "cache"
    with pytest.raises(dl.DownloadCancelled):
        dl.download_patched(cache_root=root, stop=stop)
    assert not any(c.endswith(name) for c in calls), "the tarball was fetched after the stop"
    assert _cache.installed_browsers(root) == []


def test_a_stop_while_installing_installs_nothing(tmp_path, monkeypatch):
    root = tmp_path / "cache"
    _install(root, OLD)
    _cache.set_current(OLD, root)
    stop = threading.Event()
    real_verify = dl.verify_binary

    def verify_then_stop(*args):
        real_verify(*args)
        stop.set()  # the launch is cancelled while the binary is hashed

    monkeypatch.setattr(dl, "verify_binary", verify_then_stop)
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    with pytest.raises(dl.DownloadCancelled):
        dl.install_from_tarball(tar, cache_root=root, stop=stop)
    assert [b.version for b in _cache.installed_browsers(root)] == [OLD]
    assert _cache.current_version(root) == OLD
    assert [p.name for p in root.iterdir() if p.name.startswith(".install-")] == []


def test_a_stoppable_download_keeps_its_network_waits_under_the_stop_timeout(tmp_path, monkeypatch):
    """The thread of a cancelled launch must not outlive the wait the launch declares."""
    stop = threading.Event()
    urlopen, _, _, timeouts = _stopping_github(tmp_path, stop, "never")
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    dl.download_patched(cache_root=tmp_path / "cache", stop=stop)
    assert timeouts and all(t is not None and t < STOP_TIMEOUT for t in timeouts), timeouts


@pytest.mark.skipif(sys.platform == "win32", reason="flock")
def test_a_lock_error_that_is_not_busy_is_raised_at_once(tmp_path, monkeypatch):
    # A filesystem without flock (ENOLCK, EINVAL) is not "held by an install":
    # no 60 s wait, and the error is the real one.
    import errno

    def no_flock(fh):
        raise OSError(errno.ENOLCK, "No locks available")

    monkeypatch.setattr(_cache, "_try_lock", no_flock)
    root = tmp_path / "cache"
    root.mkdir()
    start = time.monotonic()
    with pytest.raises(OSError, match="No locks available"):
        with _cache.reading_lock(root):
            pass
    assert time.monotonic() - start < 1

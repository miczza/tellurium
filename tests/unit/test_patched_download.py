"""Tests for chromium-telluride release download/install (no network)."""

import hashlib
import io
import json
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tellurium.browser import _cache
from tellurium.browser import _patched_download as dl
from tellurium.browser._manifest import current_platform

VERSION = "146.0.7680.188"
BINARY = b"\x7fELF fake chromium-telluride binary"


def _manifest(binary=BINARY, version=VERSION):
    return {
        "data_version": "1.0",
        "version": "0.1.0",
        "previous": "",
        "chromium_upstream": version,
        "released_at": "2026-04-28T11:37:33Z",
        "security": False,
        "cve": [],
        "severity": "none",
        "binary_sha256": {current_platform(): hashlib.sha256(binary).hexdigest()},
        "supported_flags": ["--fingerprint", "--fingerprint-platform", "--fingerprint-webrtc-ip"],
    }


def _make_tarball(
    path: Path, manifest: dict | None = None, binary=BINARY, extra: dict[str, bytes] | None = None
) -> Path:
    manifest = manifest if manifest is not None else _manifest(binary)
    files = {
        "chrome": binary,
        "MANIFEST.json": json.dumps(manifest).encode(),
        "icudtl.dat": b"icu",
        "locales/en-US.pak": b"pak",
    }
    files.update(extra or {})
    with tarfile.open(path, "w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(f"chromium-telluride/{name}")
            info.size = len(data)
            info.mode = 0o755 if name == "chrome" else 0o644
            tf.addfile(info, io.BytesIO(data))
    return path


# --------------------------------------------------------------------------- #
# install_from_tarball
# --------------------------------------------------------------------------- #


def test_install_from_tarball_layout(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    root = tmp_path / "cache"
    entry = dl.install_from_tarball(tar, cache_root=root)

    assert entry.version == VERSION
    assert entry.binary == root / VERSION / "chrome"
    assert (root / VERSION / "MANIFEST.json").is_file()
    assert (root / VERSION / "locales" / "en-US.pak").is_file()
    assert entry.binary.stat().st_mode & 0o111
    assert _cache.current_version(root) == VERSION
    assert entry.is_current
    # No staging leftovers
    leftovers = [p.name for p in root.iterdir() if p.name.startswith(".")]
    assert leftovers in ([], [_cache.LOCK_NAME])


def test_install_from_tarball_matches_engine_resolution(tmp_path):
    """The directory produced by the installer must be what PatchedEngine reads."""
    from tellurium.browser.engine import PatchedEngine

    tar = _make_tarball(tmp_path / "rel.tar.gz")
    root = tmp_path / "cache"
    dl.install_from_tarball(tar, cache_root=root)

    pinned = PatchedEngine(cache_root=root, chromium_version=VERSION)
    assert pinned.resolve_binary_path() == root / VERSION / "chrome"

    with patch("tellurium.browser._update_check.check_for_update", return_value=None):
        default = PatchedEngine(cache_root=root)
        assert default.resolve_binary_path().resolve() == (root / VERSION / "chrome").resolve()


def test_install_rejects_binary_hash_mismatch(tmp_path):
    from tellurium.browser.engine import BinaryCorruptedError

    tar = _make_tarball(tmp_path / "rel.tar.gz", manifest=_manifest(binary=b"other"))
    with pytest.raises(BinaryCorruptedError):
        dl.install_from_tarball(tar, cache_root=tmp_path / "cache")
    assert not (tmp_path / "cache" / VERSION).exists()


def test_install_rejects_tarball_hash_mismatch(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    with pytest.raises(dl.DownloadError, match="Tarball SHA256"):
        dl.install_from_tarball(
            tar, cache_root=tmp_path / "cache", expected_tarball_sha256="00" * 32
        )


def test_install_rejects_path_traversal(tmp_path):
    tar = tmp_path / "evil.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        info = tarfile.TarInfo("chromium-telluride/../../evil")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(dl.DownloadError, match="unsafe"):
        dl.install_from_tarball(tar, cache_root=tmp_path / "cache")


def test_install_replaces_existing_version(tmp_path):
    root = tmp_path / "cache"
    old = root / VERSION
    old.mkdir(parents=True)
    (old / "chrome").write_bytes(b"corrupt")
    (old / "stale.txt").write_text("x")
    dl.install_from_tarball(_make_tarball(tmp_path / "rel.tar.gz"), cache_root=root)
    assert (old / "chrome").read_bytes() == BINARY
    assert not (old / "stale.txt").exists()


def test_install_without_manifest_refused(tmp_path):
    tar = tmp_path / "nomanifest.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        info = tarfile.TarInfo("chromium-telluride/chrome")
        info.size = len(BINARY)
        tf.addfile(info, io.BytesIO(BINARY))
    with pytest.raises(dl.DownloadError, match="MANIFEST"):
        dl.install_from_tarball(tar, cache_root=tmp_path / "cache")


# --------------------------------------------------------------------------- #
# GitHub release resolution + download (urlopen mocked)
# --------------------------------------------------------------------------- #


class _Resp:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._buf = io.BytesIO(body)
        self.headers = headers or {"Content-Length": str(len(body))}

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None


def _fake_github(tmp_path, tarball: Path, *, with_sums=True, tag=f"v0.1.0-{VERSION}"):
    plat = current_platform()
    name = f"chromium-telluride-{VERSION}-{plat}.tar.gz"
    base = "https://example.invalid/dl"
    assets = [
        {"name": name, "browser_download_url": f"{base}/{name}"},
        {"name": "MANIFEST.json", "browser_download_url": f"{base}/MANIFEST.json"},
    ]
    if with_sums:
        assets.append({"name": "SHA256SUMS", "browser_download_url": f"{base}/SHA256SUMS"})
    release = {"tag_name": tag, "assets": assets}
    tar_bytes = tarball.read_bytes()
    sums = f"{hashlib.sha256(tar_bytes).hexdigest()}  {name}\n".encode()
    calls: list[str] = []

    def urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        calls.append(url)
        if url.endswith("/releases/latest"):
            return _Resp(json.dumps(release).encode())
        if "/releases?" in url:
            return _Resp(
                json.dumps([{"tag_name": "v0.2.0-999.0.0.0", "assets": []}, release]).encode()
            )
        if url.endswith(name):
            return _Resp(tar_bytes)
        if url.endswith("SHA256SUMS"):
            return _Resp(sums)
        raise AssertionError(f"unexpected url {url}")

    return urlopen, calls, name


def test_download_patched_latest(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    urlopen, calls, name = _fake_github(tmp_path, tar)
    root = tmp_path / "cache"
    progress = []
    with patch("urllib.request.urlopen", urlopen):
        entry = dl.download_patched(cache_root=root, progress=lambda d, t: progress.append((d, t)))
    assert entry.version == VERSION
    assert entry.binary.read_bytes() == BINARY
    assert any(c.endswith(name) for c in calls)
    assert progress and progress[-1][0] == tar.stat().st_size
    assert [p for p in root.iterdir() if p.name.startswith(".download-")] == []


def test_download_patched_specific_version_scans_releases(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    urlopen, calls, _ = _fake_github(tmp_path, tar)
    with patch("urllib.request.urlopen", urlopen):
        entry = dl.download_patched(VERSION, cache_root=tmp_path / "cache")
    assert entry.version == VERSION
    assert any("/releases?" in c for c in calls)


def test_download_patched_unknown_version(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    urlopen, _, _ = _fake_github(tmp_path, tar)
    with patch("urllib.request.urlopen", urlopen):
        with pytest.raises(dl.DownloadError, match="No chromium-telluride release"):
            dl.download_patched("1.2.3.4", cache_root=tmp_path / "cache")


def test_download_patched_tarball_sha_checked(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    urlopen, _, name = _fake_github(tmp_path, tar)

    def bad_sums(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if url.endswith("SHA256SUMS"):
            return _Resp(f"{'00' * 32}  {name}\n".encode())
        return urlopen(req, timeout)

    with patch("urllib.request.urlopen", bad_sums):
        with pytest.raises(dl.DownloadError, match="Tarball SHA256"):
            dl.download_patched(cache_root=tmp_path / "cache")


def test_latest_version_parses_tag(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    urlopen, _, _ = _fake_github(tmp_path, tar)
    with patch("urllib.request.urlopen", urlopen):
        assert dl.latest_version() == VERSION


def test_reinstall_keeps_current_flag(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    root = tmp_path / "cache"
    dl.install_from_tarball(tar, cache_root=root)
    (root / VERSION / "chrome").write_bytes(b"corrupted")
    urlopen, _, _ = _fake_github(tmp_path, tar)
    with patch("urllib.request.urlopen", urlopen):
        entry = dl.reinstall(VERSION, cache_root=root)
    assert entry.binary.read_bytes() == BINARY
    assert entry.is_current


# --------------------------------------------------------------------------- #
# Hostile releases (audit M9, m2)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "hostile", ["../../Documents", "{abs}/home/Documents", "146.0.7680.188/..", ""]
)
def test_install_refuses_a_hostile_install_dir(tmp_path, hostile):
    hostile = hostile.format(abs=tmp_path)
    home = tmp_path / "home"
    victim = home / "Documents"
    victim.mkdir(parents=True)
    (victim / "thesis.docx").write_text("precious")
    manifest = _manifest()
    manifest["chromium_upstream"] = hostile
    manifest["version"] = hostile
    tar = _make_tarball(tmp_path / "evil.tar.gz", manifest=manifest)
    root = home / ".tellurium" / "chromium"
    with pytest.raises(dl.DownloadError, match="install dir"):
        dl.install_from_tarball(tar, cache_root=root)
    assert (victim / "thesis.docx").read_text() == "precious"
    assert [p.name for p in root.iterdir()] == []  # staging removed too


def test_reinstall_refuses_a_hostile_version(tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    root = tmp_path / "cache"
    root.mkdir()
    with pytest.raises(dl.DownloadError, match="version"):
        dl.reinstall("../victim", cache_root=root)
    assert victim.exists()


def test_set_current_refuses_a_hostile_version(tmp_path):
    with pytest.raises(ValueError, match="version"):
        _cache.set_current("../../etc", tmp_path)


def test_install_handles_hardlinks_under_the_top_dir(tmp_path):
    tar = tmp_path / "hardlink.tar.gz"
    manifest = json.dumps(_manifest()).encode()
    with tarfile.open(tar, "w:gz") as tf:
        for name, data in (("chrome", BINARY), ("MANIFEST.json", manifest), ("libfoo.so", b"lib")):
            info = tarfile.TarInfo(f"chromium-telluride/{name}")
            info.size = len(data)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("chromium-telluride/libbar.so")
        link.type = tarfile.LNKTYPE
        link.linkname = "chromium-telluride/libfoo.so"
        tf.addfile(link)
    entry = dl.install_from_tarball(tar, cache_root=tmp_path / "cache")
    assert (entry.path / "libbar.so").read_bytes() == b"lib"


def test_install_refuses_a_hardlink_out_of_the_top_dir(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    with tarfile.open(tar, "r:gz") as src:
        members = [(m, src.extractfile(m).read() if m.isfile() else None) for m in src]
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tf:
        for m, data in members:
            tf.addfile(m, io.BytesIO(data) if data is not None else None)
        link = tarfile.TarInfo("chromium-telluride/escape")
        link.type = tarfile.LNKTYPE
        link.linkname = "etc/passwd"  # outside chromium-telluride/
        tf.addfile(link)
    with pytest.raises(dl.DownloadError, match="unsafe"):
        dl.install_from_tarball(evil, cache_root=tmp_path / "cache")


def test_download_without_sha256sums_is_refused(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    urlopen, _, _ = _fake_github(tmp_path, tar, with_sums=False)
    root = tmp_path / "cache"
    with patch("urllib.request.urlopen", urlopen):
        with pytest.raises(dl.DownloadError, match="SHA256SUMS"):
            dl.download_patched(cache_root=root)
        assert _cache.installed_browsers(root) == []
        entry = dl.download_patched(cache_root=root, allow_unverified=True)
    assert entry.version == VERSION


def test_download_with_unreachable_sha256sums_is_refused(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    urlopen, _, _ = _fake_github(tmp_path, tar)

    def broken_sums(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if url.endswith("SHA256SUMS"):
            raise OSError("network down")
        return urlopen(req, timeout)

    with patch("urllib.request.urlopen", broken_sums):
        with pytest.raises(dl.DownloadError, match="SHA256SUMS"):
            dl.download_patched(cache_root=tmp_path / "cache")


def test_download_with_tarball_missing_from_sha256sums_is_refused(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    urlopen, _, _ = _fake_github(tmp_path, tar)

    def other_sums(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if url.endswith("SHA256SUMS"):
            return _Resp(f"{'ab' * 32}  something-else.tar.gz\n".encode())
        return urlopen(req, timeout)

    with patch("urllib.request.urlopen", other_sums):
        with pytest.raises(dl.DownloadError, match="SHA256SUMS"):
            dl.download_patched(cache_root=tmp_path / "cache")


# --------------------------------------------------------------------------- #
# Concurrent installs (two launches with auto_security_update, CLI + launch)
# --------------------------------------------------------------------------- #


def _hammer(n_threads: int, rounds: int, job) -> list[BaseException]:
    import threading

    errors: list[BaseException] = []
    start = threading.Barrier(n_threads)

    def run() -> None:
        start.wait()
        for _ in range(rounds):
            try:
                job()
            except BaseException as e:  # noqa: BLE001 — collected for the assert
                errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


def test_concurrent_installs_of_one_release_all_succeed(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    root = tmp_path / "cache"
    errors = _hammer(3, 8, lambda: dl.install_from_tarball(tar, cache_root=root))
    assert errors == []
    assert (root / VERSION / "chrome").read_bytes() == BINARY
    assert _cache.current_version(root) == VERSION
    assert [p.name for p in root.iterdir() if p.is_dir() and p.name != "current"] == [VERSION]


def test_reinstalling_the_same_release_keeps_the_running_install(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    root = tmp_path / "cache"
    first = dl.install_from_tarball(tar, cache_root=root)
    inode = first.binary.stat().st_ino
    dl.install_from_tarball(tar, cache_root=root)
    assert (root / VERSION / "chrome").stat().st_ino == inode  # not yanked from under Chrome


def test_concurrent_set_current_never_fails(tmp_path):
    for v in ("146.0.7680.188", "147.0.7700.10"):
        (tmp_path / v).mkdir()
    flip = iter(range(10**9))

    def job() -> None:
        _cache.set_current(("146.0.7680.188", "147.0.7700.10")[next(flip) % 2], tmp_path)

    assert _hammer(2, 300, job) == []
    assert _cache.current_version(tmp_path) in ("146.0.7680.188", "147.0.7700.10")


def test_install_filesystem_errors_become_download_errors(tmp_path, monkeypatch):
    tar = _make_tarball(tmp_path / "rel.tar.gz")

    def no_space(*a, **kw):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(dl, "_safe_extract", no_space)
    with pytest.raises(dl.DownloadError, match="No space left"):
        dl.install_from_tarball(tar, cache_root=tmp_path / "cache")


def test_a_failed_reinstall_keeps_the_installed_version(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    root = tmp_path / "cache"
    dl.install_from_tarball(tar, cache_root=root)
    urlopen, _, _ = _fake_github(tmp_path, tar, with_sums=False)
    with patch("urllib.request.urlopen", urlopen):
        with pytest.raises(dl.DownloadError, match="SHA256SUMS"):
            dl.reinstall(VERSION, cache_root=root)
        assert (root / VERSION / "chrome").read_bytes() == BINARY  # still usable
        assert _cache.current_version(root) == VERSION
        (root / VERSION / "chrome").write_bytes(b"corrupted")
        entry = dl.reinstall(VERSION, cache_root=root, allow_unverified=True)
    assert entry.binary.read_bytes() == BINARY


def test_reinstall_replaces_even_an_identical_binary(tmp_path):
    tar = _make_tarball(tmp_path / "rel.tar.gz")
    root = tmp_path / "cache"
    dl.install_from_tarball(tar, cache_root=root)
    (root / VERSION / "locales" / "en-US.pak").write_bytes(b"broken")
    urlopen, _, _ = _fake_github(tmp_path, tar)
    with patch("urllib.request.urlopen", urlopen):
        dl.reinstall(VERSION, cache_root=root)
    assert (root / VERSION / "locales" / "en-US.pak").read_bytes() == b"pak"

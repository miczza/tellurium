"""Chrome for Testing installs: version order (m4), archive extraction (m3),
and version detection on Windows (m8)."""

from __future__ import annotations

import os
import shutil
import stat
import sys
import zipfile
from pathlib import Path

import pytest

from tellurium.browser import launcher


def _install(base: Path, version: str) -> Path:
    binary = base / f"chrome-{version}" / "chrome"
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    return binary


def test_managed_installs_are_ordered_by_version_not_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "_tellurium_browsers_dir", lambda: tmp_path)
    for version in ("99.0.4844.51", "140.0.7339.80", "140.0.7339.207", "131.0.6778.85"):
        _install(tmp_path, version)

    found = [Path(path).parent.name for path, _ in launcher._find_cft_managed()]

    assert found == [
        "chrome-140.0.7339.207",
        "chrome-140.0.7339.80",
        "chrome-131.0.6778.85",
        "chrome-99.0.4844.51",
    ]


def _zip_entry(zf: zipfile.ZipFile, name: str, data: bytes, mode: int) -> None:
    info = zipfile.ZipInfo(name)
    info.create_system = 3  # Unix: external_attr carries st_mode
    info.external_attr = mode << 16
    zf.writestr(info, data)


def _cft_zip(path: Path, extra: list[tuple[str, bytes, int]] = ()) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        _zip_entry(zf, "chrome-linux64/chrome", b"#!/bin/sh\n", stat.S_IFREG | 0o755)
        _zip_entry(zf, "chrome-linux64/chrome_crashpad_handler", b"x", stat.S_IFREG | 0o755)
        _zip_entry(zf, "chrome-linux64/resources.pak", b"x", stat.S_IFREG | 0o644)
        _zip_entry(zf, "chrome-linux64/Versions/A/lib", b"x", stat.S_IFREG | 0o644)
        _zip_entry(zf, "chrome-linux64/Versions/Current", b"A", stat.S_IFLNK | 0o777)
        for name, data, mode in extra:
            _zip_entry(zf, name, data, mode)
    return path


@pytest.fixture
def fake_download(tmp_path, monkeypatch):
    """download_cft() fetching a local archive instead of the CfT bucket."""
    import urllib.request

    archive = {"path": _cft_zip(tmp_path / "src.zip")}
    browsers = tmp_path / "browsers"
    monkeypatch.setattr(launcher, "_tellurium_browsers_dir", lambda: browsers)
    monkeypatch.setattr(launcher, "_determine_platform", lambda: "linux64")
    monkeypatch.setattr(
        urllib.request, "urlretrieve", lambda url, dest: shutil.copy(archive["path"], dest)
    )
    return archive, browsers


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes and symlinks")
async def test_download_keeps_exec_bits_and_symlinks(fake_download):
    _, browsers = fake_download

    binary = Path(await launcher.download_cft("140.0.7339.80"))

    root = browsers / "chrome-140.0.7339.80" / "chrome-linux64"
    assert binary == root / "chrome"
    assert os.access(root / "chrome_crashpad_handler", os.X_OK)
    assert not os.access(root / "resources.pak", os.X_OK)
    assert (root / "Versions" / "Current").is_symlink()
    assert os.readlink(root / "Versions" / "Current") == "A"
    assert (root / "Versions" / "Current" / "lib").is_file()


@pytest.mark.parametrize(
    "entries",
    [
        [("../escape", b"x", stat.S_IFREG | 0o644)],
        [("/abs/escape", b"x", stat.S_IFREG | 0o644)],
        [
            ("chrome-linux64/out", b"../../..", stat.S_IFLNK | 0o777),
            ("chrome-linux64/out/escape", b"x", stat.S_IFREG | 0o644),
        ],
    ],
    ids=["dotdot", "absolute", "through-symlink"],
)
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
async def test_download_refuses_entries_outside_the_install_dir(fake_download, tmp_path, entries):
    await _assert_refused(fake_download, tmp_path, entries)


@pytest.mark.parametrize(
    "entries",
    [
        [("chrome-linux64/abs", b"/etc", stat.S_IFLNK | 0o777)],
        [("chrome-linux64/up", b"../../outside", stat.S_IFLNK | 0o777)],
        [("chrome-linux64/deep/up", b"../../../x", stat.S_IFLNK | 0o777)],
        [  # lexically inside, but the kernel resolves s1 before the '..'
            ("chrome-linux64/a/b/s1", b"../..", stat.S_IFLNK | 0o777),
            ("chrome-linux64/a/b/l", b"s1/../../../../escape", stat.S_IFLNK | 0o777),
        ],
        [  # same chain, the link written before the link it climbs through
            ("chrome-linux64/a/b/l", b"s1/../../../../escape", stat.S_IFLNK | 0o777),
            ("chrome-linux64/a/b/s1", b"../..", stat.S_IFLNK | 0o777),
        ],
    ],
    ids=["absolute", "relative-escape", "nested-escape", "link-chain", "link-chain-reversed"],
)
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
async def test_download_refuses_symlinks_pointing_outside(fake_download, tmp_path, entries):
    """A link to /etc (or ../..) would later be followed by chmod or by Chrome."""
    await _assert_refused(fake_download, tmp_path, entries)


async def _assert_refused(fake_download, tmp_path, entries):
    archive, browsers = fake_download
    archive["path"] = _cft_zip(tmp_path / "evil.zip", entries)

    with pytest.raises(ValueError, match="outside"):
        await launcher.download_cft("140.0.7339.80")
    assert not (tmp_path / "escape").exists()
    assert not (browsers / "escape").exists()
    # Nothing half-extracted is left for _find_cft_managed to pick up.
    assert not (browsers / "chrome-140.0.7339.80").exists()
    assert list(browsers.iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")
async def test_a_failed_reinstall_keeps_the_previous_install(fake_download, tmp_path):
    archive, browsers = fake_download
    good = Path(await launcher.download_cft("140.0.7339.80"))
    archive["path"] = _cft_zip(tmp_path / "evil.zip", [("../escape", b"x", stat.S_IFREG)])

    with pytest.raises(ValueError):
        await launcher.download_cft("140.0.7339.80")

    assert good.is_file()
    assert [p.name for p in browsers.iterdir()] == ["chrome-140.0.7339.80"]

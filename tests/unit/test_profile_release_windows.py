"""On Windows Chrome marks the profile it holds with ``lockfile``, open for
writing and shared for reading only, deleted when it lets go."""

from __future__ import annotations

import sys

import pytest

from tellurium.session import profile_release

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Chrome's Windows lockfile")

_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x1
_CREATE_ALWAYS = 2
_FILE_FLAG_DELETE_ON_CLOSE = 0x04000000


def _hold_like_chrome(chrome_dir):
    import _winapi

    chrome_dir.mkdir(exist_ok=True)
    return _winapi.CreateFile(
        str(chrome_dir / "lockfile"),
        _GENERIC_WRITE,
        _FILE_SHARE_READ,
        0,
        _CREATE_ALWAYS,
        _FILE_FLAG_DELETE_ON_CLOSE,
        0,
    )


async def test_a_held_lockfile_is_a_chrome_on_the_profile(tmp_path):
    import _winapi

    handle = _hold_like_chrome(tmp_path / "chrome")
    try:
        assert await profile_release.wait(str(tmp_path / "chrome"), 0.3) is not None
    finally:
        _winapi.CloseHandle(handle)
    assert not (tmp_path / "chrome" / "lockfile").exists()
    assert await profile_release.wait(str(tmp_path / "chrome"), 1.0) is None


async def test_a_lockfile_nobody_holds_is_free(tmp_path):
    (tmp_path / "chrome").mkdir()
    (tmp_path / "chrome" / "lockfile").write_bytes(b"")  # left by a Chrome that crashed
    assert await profile_release.wait(str(tmp_path / "chrome"), 1.0) is None
    assert await profile_release.wait(str(tmp_path / "missing"), 1.0) is None

"""A real Chrome rewrites its process title (``/proc/<pid>/cmdline`` becomes
one string of space-joined arguments): profile_release must still see it hold
its profile while it lives, and let go once it has closed."""

from __future__ import annotations

import os
import sys

import pytest

from tellurium import Browser
from tellurium.session import profile_release

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or not os.path.isdir("/proc"), reason="SingletonLock and /proc"
)


def _lock_pid(chrome_dir) -> int:
    return int(os.readlink(os.path.join(chrome_dir, "SingletonLock")).rpartition("-")[2])


async def test_a_live_chrome_holds_its_profile_until_it_closes(tmp_path):
    real = tmp_path / "with space"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    chrome_dir = real / "chrome dir"
    browser = await Browser.launch(user_data_dir=str(chrome_dir), headless=True)
    try:
        pid = _lock_pid(chrome_dir)
        assert await profile_release.wait(str(chrome_dir), 0.3) == pid
        seen = str(tmp_path / "link" / "chrome dir")  # the same profile, by another path
        assert await profile_release.wait(seen, 0.3) == pid
        sibling = str(real / "chrome")  # a prefix of it is another profile
        os.makedirs(sibling)
        os.symlink(
            os.readlink(os.path.join(chrome_dir, "SingletonLock")),
            os.path.join(sibling, "SingletonLock"),
        )
        assert await profile_release.wait(sibling, 0.3) is None
    finally:
        await browser.close()
    assert await profile_release.wait(str(chrome_dir), 10.0) is None

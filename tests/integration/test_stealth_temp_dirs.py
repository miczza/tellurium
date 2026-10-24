"""A stealth launch leaves no temporary directory behind (its extension
included), after close() and after a failed launch."""

from __future__ import annotations

import gc
import shutil
import tempfile
from pathlib import Path

import pytest

from tellurium import Browser, LaunchError


@pytest.fixture
def isolated_tmp(monkeypatch):
    # Short: Chrome's singleton socket path under TMPDIR has a length limit.
    path = Path(tempfile.mkdtemp(prefix="ts", dir="/tmp"))
    monkeypatch.setattr(tempfile, "tempdir", str(path))
    yield path
    shutil.rmtree(path, ignore_errors=True)


async def test_stealth_launch_and_close_leave_no_temp_dirs(isolated_tmp):
    browser = await Browser.launch(headless=True, stealth=True)
    assert any(p.name.startswith("tellurium_ext_") for p in isolated_tmp.iterdir())
    await browser.close()
    del browser
    gc.collect()
    assert list(isolated_tmp.iterdir()) == []


async def test_failed_stealth_launch_leaves_no_temp_dirs(isolated_tmp):
    with pytest.raises(LaunchError):
        await Browser.launch(headless=True, stealth=True, executable="/bin/false")
    gc.collect()
    assert list(isolated_tmp.iterdir()) == []

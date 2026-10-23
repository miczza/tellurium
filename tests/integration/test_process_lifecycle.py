"""Chrome process lifecycle: output handling, launch rollback, no leaks.

Covers the audit findings B1 (unread stdout/stderr pipes freeze Chrome),
M5 (a failed or cancelled launch leaks the process, the temp profile and the
proxy forwarder, and hides Chrome's own error) and M10 (fds leak on every
launch/close cycle).
"""

from __future__ import annotations

import asyncio
import glob
import os
import sys
import tempfile
from pathlib import Path

import pytest

from tellurium import Browser
from tellurium.browser.launcher import LaunchError

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="uses /proc to observe processes and fds"
)

VERBOSE = ["--enable-logging=stderr", "--v=1"]


def _children() -> set[int]:
    """Direct children of this process (zombies included until reaped)."""
    pids: set[int] = set()
    for path in glob.glob(f"/proc/{os.getpid()}/task/*/children"):
        try:
            pids.update(int(p) for p in Path(path).read_text().split())
        except OSError:
            pass
    return pids


@pytest.fixture(autouse=True)
def private_tempdir(tmp_path, monkeypatch):
    """Temp profiles go to a directory of this test alone: other tellurium
    runs on the machine create ``tellurium_*`` dirs in /tmp concurrently."""
    root = tmp_path / "tempdir"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))


def _temp_profiles() -> set[str]:
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "tellurium_*")))


def _open_fds() -> int:
    return len(os.listdir(f"/proc/{os.getpid()}/fd"))


async def _wait_until(predicate, timeout: float = 5.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


def _fake_chrome(tmp_path: Path, stderr: str, code: int) -> str:
    script = tmp_path / "fake-chrome"
    script.write_text(f"#!/bin/sh\necho '{stderr}' >&2\nexit {code}\n")
    script.chmod(0o755)
    return str(script)


# ---------------------------------------------------------------------------
# B1 — Chrome output never blocks the browser
# ---------------------------------------------------------------------------


async def test_verbose_chrome_logging_does_not_freeze_the_browser(local_server):
    """Spec R1, outcome 1: 200 pages with verbose logging, no freeze."""
    browser = await Browser.launch(headless=True, args=VERBOSE)
    try:

        async def scrape() -> None:
            for i in range(200):
                await browser.main_tab.get(f"{local_server}/basic.html?page={i}")

        await asyncio.wait_for(scrape(), timeout=120)
    finally:
        await browser.close()


async def test_chrome_log_goes_to_the_requested_file(local_server, tmp_path):
    log = tmp_path / "chrome.log"
    browser = await Browser.launch(headless=True, args=VERBOSE, chrome_log=log)
    try:
        await asyncio.wait_for(browser.main_tab.get(f"{local_server}/basic.html"), timeout=30)
    finally:
        await browser.close()
    assert log.stat().st_size > 0


# ---------------------------------------------------------------------------
# M5 — launch is one transaction: rollback on failure and cancellation
# ---------------------------------------------------------------------------


async def test_failed_launch_reports_chrome_error_and_cleans_up(tmp_path):
    executable = _fake_chrome(tmp_path, "boom: libfoo.so missing", 3)
    children, profiles = _children(), _temp_profiles()

    with pytest.raises(LaunchError) as info:
        await asyncio.wait_for(Browser.launch(headless=True, executable=executable), 30)

    message = str(info.value)
    assert "boom: libfoo.so missing" in message
    assert "exit code 3" in message
    assert _children() <= children, "the failed Chrome process was not reaped"
    assert _temp_profiles() <= profiles, "the temporary profile was left behind"


async def test_profile_already_in_use_says_so(tmp_path):
    profile = str(tmp_path / "profile")
    first = await Browser.launch(headless=True, user_data_dir=profile)
    try:
        with pytest.raises(LaunchError) as info:
            await asyncio.wait_for(Browser.launch(headless=True, user_data_dir=profile), 30)
        assert "profile" in str(info.value).lower()
        # The first browser is untouched by the failed second launch.
        assert await asyncio.wait_for(first.main_tab.eval("1 + 1"), 10) == 2
    finally:
        await first.close()


async def test_cancelled_launch_leaves_nothing_behind(monkeypatch):
    from tellurium.browser import proxy as proxy_mod

    stopped: list[object] = []
    real_stop = proxy_mod.ProxyForwarder.stop

    async def spy_stop(self):
        stopped.append(self)
        await real_stop(self)

    monkeypatch.setattr(proxy_mod.ProxyForwarder, "stop", spy_stop)
    children, profiles = _children(), _temp_profiles()

    task = asyncio.ensure_future(
        Browser.launch(headless=True, proxy="http://user:secret@127.0.0.1:9")
    )
    assert await _wait_until(lambda: _children() - children, timeout=15), "Chrome never started"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await _wait_until(lambda: _children() <= children), "Chrome survived the cancel"
    assert _temp_profiles() <= profiles, "the temporary profile was left behind"
    assert stopped, "the proxy forwarder was left running"


# ---------------------------------------------------------------------------
# M10 — launch/close cycles leak no fds, processes or profiles
# ---------------------------------------------------------------------------


async def test_launch_close_cycles_leak_nothing():
    async def cycle() -> None:
        browser = await Browser.launch(headless=True)
        await browser.close()

    await cycle()  # warm-up: lazily created loop resources
    children, profiles, fds = _children(), _temp_profiles(), _open_fds()
    for _ in range(3):
        await cycle()

    assert _open_fds() == fds, f"fds leaked: {fds} -> {_open_fds()}"
    assert _children() <= children
    assert _temp_profiles() <= profiles

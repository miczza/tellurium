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
import shutil
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from tellurium import Browser
from tellurium.browser import process as process_module
from tellurium.browser.launch_plan import LaunchPlan
from tellurium.browser.launcher import LaunchError
from tellurium.browser.process import BrowserProcess
from tests.platform_marks import needs_proc

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
def private_tempdir(monkeypatch, tmp_path_factory):
    """Temp files go to a directory of this test alone: other tellurium
    runs on the machine create ``tellurium_*`` dirs in /tmp concurrently.
    TMPDIR too, so whatever Chrome would leave in the system temp dir shows.
    Short on purpose: Chrome's singleton socket path must fit in 108 bytes."""
    tmp_path_factory.getbasetemp()  # pytest's own temp root, fixed before the patch
    root = Path(tempfile.mkdtemp(prefix="tlr", dir="/tmp"))
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    monkeypatch.setenv("TMPDIR", str(root))
    yield root
    shutil.rmtree(root, ignore_errors=True)


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


@pytest.mark.parametrize("args", [VERBOSE, None], ids=["verbose", "default"])
async def test_chrome_log_goes_to_the_requested_file(local_server, tmp_path, args):
    """Also on Windows, where a release chrome.exe writes nothing to its standard
    error unless told to: with chrome_log it is (E2). Chrome's temporary
    directory is ours and goes with the browser."""
    log = tmp_path / "chrome.log"
    browser = await Browser.launch(headless=True, args=args, chrome_log=log)
    chrome_tmp = Path(browser._proc.chrome_tmp)
    try:
        assert chrome_tmp.is_dir()
        await asyncio.wait_for(browser.main_tab.get(f"{local_server}/basic.html"), timeout=30)
    finally:
        await browser.close()
    assert log.is_file()
    if args or sys.platform == "win32":  # elsewhere Chrome's default output may be empty
        assert log.stat().st_size > 0
    assert not chrome_tmp.exists()


class TestWhatTheLaunchHandsToChrome:
    """The environment and the temporary directory of a launch, on every system."""

    @pytest.fixture(autouse=True)
    def private_tempdir(self, tmp_path):
        """These tests look at named paths only: the system's temp dir is enough."""
        yield tmp_path

    async def test_the_environment_of_the_launch_reaches_chrome(self, tmp_path):
        """CHROME_LOG_FILE names where ``--enable-logging`` writes: given as the
        launch's *env*, it shows that Chrome got it (on Windows through our own
        environment block). The temporary directory goes at close."""
        log = tmp_path / "from-env.log"
        proc, plan = BrowserProcess(), LaunchPlan(headless=True)
        try:
            await plan.compose(proc)
            flags = [*plan.flags, "--enable-logging", "--v=1"]
            await proc.spawn(plan.chrome_path, flags, None, {"CHROME_LOG_FILE": str(log)})
            chrome_tmp = Path(proc.chrome_tmp)
            assert chrome_tmp.is_dir() and chrome_tmp.parent == Path(tempfile.gettempdir())
            assert await _wait_until(lambda: log.is_file() and log.stat().st_size > 0, 30)
        finally:
            await proc.close()
        assert not chrome_tmp.exists()


# ---------------------------------------------------------------------------
# M5 — launch is one transaction: rollback on failure and cancellation
# ---------------------------------------------------------------------------


@needs_proc
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


@needs_proc
async def test_a_mute_chrome_times_out_naming_the_command(tmp_path, monkeypatch):
    """Chrome alive but never answering: launch() fails by itself, no wait_for needed."""
    from tellurium.cdp.transport._session import SessionRouter

    script = tmp_path / "mute-chrome"
    script.write_text("#!/bin/sh\nexec sleep 60\n")
    script.chmod(0o755)
    monkeypatch.setattr(SessionRouter, "default_timeout", 0.5)
    monkeypatch.setattr(process_module, "READY_TIMEOUT", 0.5)
    children, profiles = _children(), _temp_profiles()

    with pytest.raises(asyncio.TimeoutError, match=r"[A-Z]\w+\.\w+ got no reply"):
        await asyncio.wait_for(Browser.launch(headless=True, executable=str(script)), 20)

    assert _children() <= children, "the mute process was not reaped"
    assert _temp_profiles() <= profiles


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


@needs_proc
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


@pytest.mark.parametrize("second_cancel_after", [0.0, 0.02, 0.08])
@needs_proc
def test_cancelling_the_rollback_again_still_releases_everything(monkeypatch, second_cancel_after):
    """A second cancel lands while the first one is being rolled back, and
    the event loop ends right after (``asyncio.run`` cancels what is left):
    no cleanup step may be skipped or left to an orphaned task."""
    from tellurium.browser import proxy as proxy_mod

    stopped: list[object] = []
    real_stop = proxy_mod.ProxyForwarder.stop

    async def spy_stop(self):
        stopped.append(self)
        await real_stop(self)

    monkeypatch.setattr(proxy_mod.ProxyForwarder, "stop", spy_stop)
    children, profiles = _children(), _temp_profiles()

    async def scenario() -> None:
        task = asyncio.ensure_future(
            Browser.launch(headless=True, proxy="http://user:secret@127.0.0.1:9")
        )
        assert await _wait_until(lambda: _children() - children, timeout=15), "no Chrome"
        task.cancel()
        await asyncio.sleep(second_cancel_after)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert _children() <= children, "Chrome survived the cancel"
    assert _temp_profiles() <= profiles, "the temporary profile was left behind"
    assert stopped, "the proxy forwarder was left running"


# ---------------------------------------------------------------------------
# M10 — launch/close cycles leak no fds, processes or profiles
# ---------------------------------------------------------------------------


def _output_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "tellurium-chrome-output"]


async def _assert_cycles_leak_nothing(tempdir: Path, cycles: int) -> None:
    async def cycle() -> None:
        browser = await Browser.launch(headless=True)
        await browser.close()

    await cycle()  # warm-up: lazily created loop resources
    children, fds = _children(), _open_fds()
    for i in range(cycles):
        await cycle()
        assert not _output_threads(), f"output thread still running after cycle {i}"

    assert _open_fds() <= fds, f"fds leaked: {fds} -> {_open_fds()}"
    assert _children() <= children
    assert not list(tempdir.iterdir()), f"left in TMPDIR: {sorted(tempdir.iterdir())[:5]}"


@needs_proc
async def test_launch_close_cycles_leak_nothing(private_tempdir):
    """fds, processes, output threads, profiles and Chrome's own temp files."""
    await _assert_cycles_leak_nothing(private_tempdir, cycles=20)


@pytest.mark.slow
@needs_proc
async def test_soak_500_launch_close_cycles(private_tempdir):
    """Spec R1, outcome 2. Out of the gate: ``TELLURIUM_SLOW=1 pytest -m slow``."""
    await _assert_cycles_leak_nothing(private_tempdir, cycles=500)

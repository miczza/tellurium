"""A dead holder's Chrome lets go of the profile a moment after its pipe closes:
the next start waits for it, and names it if it never does."""

from __future__ import annotations

import os
import socket
import subprocess
import sys

import pytest

from tellurium.session import profile_release

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="SingletonLock is POSIX")


def _link(chrome_dir, pid, host=None):
    chrome_dir.mkdir(exist_ok=True)
    os.symlink(f"{host or socket.gethostname()}-{pid}", chrome_dir / "SingletonLock")


async def test_no_lock_is_free(tmp_path):
    assert await profile_release.wait(str(tmp_path / "chrome"), 1.0) is None


async def test_dead_holder_is_free(tmp_path):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    _link(tmp_path / "chrome", dead.pid)
    assert await profile_release.wait(str(tmp_path / "chrome"), 1.0) is None


async def test_holder_on_another_host_is_left_to_chrome(tmp_path):
    _link(tmp_path / "chrome", os.getpid(), host="elsewhere.invalid")
    assert await profile_release.wait(str(tmp_path / "chrome"), 1.0) is None


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc")
async def test_a_reused_pid_is_not_a_chrome_of_this_profile(tmp_path):
    _link(tmp_path / "chrome", os.getpid())  # alive, but not started on this profile
    assert await profile_release.wait(str(tmp_path / "chrome"), 1.0) is None


def _fake_chrome(chrome_dir, seconds):
    """A process started on *chrome_dir*, once it runs (as Chrome is when it
    writes its SingletonLock: right after exec its argv may not be mapped yet)."""
    code = f"import time; print(flush=True); time.sleep({seconds})"
    argv = [sys.executable, "-c", code, f"--user-data-dir={chrome_dir}"]
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE)
    proc.stdout.readline()
    return proc


async def test_waits_for_a_chrome_that_is_exiting(tmp_path):
    chrome_dir = tmp_path / "chrome"
    chrome_dir.mkdir()
    proc = _fake_chrome(chrome_dir, 0.3)
    try:
        _link(chrome_dir, proc.pid)
        assert await profile_release.wait(str(chrome_dir), 10.0) is None
        assert proc.poll() is not None or proc.wait(1) is not None
    finally:
        proc.kill()
        proc.wait()


async def test_a_chrome_that_stays_is_named(tmp_path):
    chrome_dir = tmp_path / "chrome"
    chrome_dir.mkdir()
    proc = _fake_chrome(chrome_dir, 30)
    try:
        _link(chrome_dir, proc.pid)
        assert await profile_release.wait(str(chrome_dir), 0.3) == proc.pid
    finally:
        proc.kill()
        proc.wait()


async def test_start_waits_for_the_profile_before_launching(tmp_path, monkeypatch):
    import tellurium
    from tellurium import Session, SessionBusyError

    order = []

    async def released(chrome_dir, timeout=profile_release.TIMEOUT):
        order.append(("wait", chrome_dir))
        return None

    async def launch(**kwargs):
        order.append(("launch", kwargs["user_data_dir"]))
        raise RuntimeError("stop here")

    monkeypatch.setattr(profile_release, "wait", released)
    monkeypatch.setattr(tellurium.Browser, "launch", launch)
    with pytest.raises(RuntimeError):
        async with Session("s", path=str(tmp_path)).start():
            pass
    chrome_dir = str(tmp_path / "chrome")
    assert order == [("wait", chrome_dir), ("launch", chrome_dir)]

    async def stuck(chrome_dir, timeout=profile_release.TIMEOUT):
        return 4242

    monkeypatch.setattr(profile_release, "wait", stuck)
    with pytest.raises(SessionBusyError) as info:
        async with Session("s", path=str(tmp_path)).start():
            pass
    assert info.value.pid == 4242
    from tellurium.session.lock import SessionLock

    assert SessionLock.holder(str(tmp_path)) is None  # released on the way out


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc")
async def test_a_chrome_seen_through_a_symlink_is_waited_for(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    chrome_dir = real / "chrome"
    chrome_dir.mkdir()
    proc = _fake_chrome(chrome_dir, 30)
    try:
        _link(chrome_dir, proc.pid)
        seen = str(tmp_path / "link" / "chrome")
        assert await profile_release.wait(seen, 0.3) == proc.pid
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc")
async def test_a_chrome_on_a_sibling_profile_is_not_ours(tmp_path):
    sibling = tmp_path / "chrome2"
    sibling.mkdir()
    proc = _fake_chrome(sibling, 30)
    try:
        _link(tmp_path / "chrome", proc.pid)  # a stale link naming a reused PID
        assert await profile_release.wait(str(tmp_path / "chrome"), 0.3) is None
    finally:
        proc.kill()
        proc.wait()


def test_user_data_dir_is_read_from_a_rewritten_title_too():
    # Chrome on Linux rewrites its title: one string of space-joined arguments.
    title = b"/opt/chrome --no-first-run --user-data-dir=/x/with space/chrome dir --headless=new\0"
    assert profile_release._user_data_dirs(title) == [b"/x/with space/chrome dir"]
    last = b"/opt/chrome --user-data-dir=/x/a b\0"
    assert profile_release._user_data_dirs(last) == [b"/x/a b"]
    argv = b"/opt/chrome\0--user-data-dir=/x/a b --c\0--headless\0"
    assert profile_release._user_data_dirs(argv) == [b"/x/a b --c"]
    assert profile_release._user_data_dirs(b"/usr/bin/python3\0-c\0pass\0") == []

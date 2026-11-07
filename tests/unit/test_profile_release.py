"""A dead holder's Chrome lets go of the profile a moment after its pipe closes:
the next start waits for it, and names it if it never does."""

from __future__ import annotations

import os
import socket
import subprocess
import sys

import pytest

from tellurium.session import process_args, profile_release

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="SingletonLock is POSIX")
#: The command line of another process: /proc on Linux, sysctl on macOS.
needs_cmdline = pytest.mark.skipif(
    sys.platform != "darwin" and not os.path.isdir("/proc"),
    reason="no way to read another process's command line here",
)


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


@needs_cmdline
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


@needs_cmdline
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


@needs_cmdline
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
    # Chrome on Linux rewrites its title: one string of space-joined arguments,
    # so a value may end at any space; the longest first.
    title = b"/opt/chrome --no-first-run --user-data-dir=/x/a b --headless=new\0"
    assert profile_release._candidates(title) == [[b"/x/a b --headless=new", b"/x/a b", b"/x/a"]]
    argv = b"/opt/chrome\0--user-data-dir=/x/a b --c\0--headless\0"
    assert profile_release._candidates(argv) == [[b"/x/a b --c"]]
    assert profile_release._candidates(b"/usr/bin/python3\0-c\0pass\0") == []


def _title(tmp_path, monkeypatch, cmdline: bytes):
    """The command line of a process that rewrote its title to *cmdline*."""
    monkeypatch.setattr(process_args, "command_line", lambda pid: cmdline)


@needs_cmdline
def test_a_title_with_a_url_after_the_profile_is_recognised(tmp_path, monkeypatch):
    chrome_dir = tmp_path / "chrome"
    chrome_dir.mkdir()
    title = f"/opt/chrome --user-data-dir={chrome_dir} https://example.test/login".encode()
    _title(tmp_path, monkeypatch, title + b"\0")
    assert profile_release._runs_on(os.getpid(), str(chrome_dir))


@needs_cmdline
def test_a_profile_path_with_a_dash_dash_is_recognised(tmp_path, monkeypatch):
    chrome_dir = tmp_path / "a --b" / "chrome"
    chrome_dir.mkdir(parents=True)
    _title(tmp_path, monkeypatch, f"/opt/chrome --user-data-dir={chrome_dir} --headless".encode())
    assert profile_release._runs_on(os.getpid(), str(chrome_dir))
    assert not profile_release._runs_on(os.getpid(), str(tmp_path / "a"))


@needs_cmdline
def test_a_prefix_of_the_profile_is_another_profile(tmp_path, monkeypatch):
    (tmp_path / "chrome").mkdir()
    (tmp_path / "chrome dir").mkdir()
    _title(tmp_path, monkeypatch, f"/opt/chrome --user-data-dir={tmp_path}/chrome dir".encode())
    assert profile_release._runs_on(os.getpid(), str(tmp_path / "chrome dir"))
    assert not profile_release._runs_on(os.getpid(), str(tmp_path / "chrome"))


@needs_cmdline
def test_the_command_line_of_a_live_process_is_read():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()", "--user-data-dir=/x/y z"],
        stdin=subprocess.PIPE,
    )
    try:
        import time

        deadline = time.monotonic() + 5
        while True:  # right after exec the arguments may not be there yet
            line = process_args.command_line(proc.pid)
            if b"--user-data-dir" in (line or b"") or time.monotonic() > deadline:
                break
            time.sleep(0.02)
        assert line.split(b"\0")[-3:] == [
            b"import sys; sys.stdin.read()",
            b"--user-data-dir=/x/y z",
            b"",
        ]
    finally:
        proc.stdin.close()
        proc.wait()
    with pytest.raises(ProcessLookupError):
        process_args.command_line(proc.pid)


@needs_cmdline
def test_an_exited_process_not_reaped_has_no_arguments():
    proc = subprocess.Popen([sys.executable, "-c", "pass", "--user-data-dir=/x"])
    try:
        import time

        deadline = time.monotonic() + 5
        while process_args.command_line(proc.pid) != process_args.ZOMBIE:
            assert time.monotonic() < deadline
            time.sleep(0.02)
    finally:
        proc.wait()


def test_a_procargs2_buffer_is_parsed():
    raw = (
        (3).to_bytes(4, sys.byteorder)
        + b"/Applications/Chrome.app/Contents/MacOS/Chrome\0\0\0\0"
        + b"Chrome\0--user-data-dir=/tmp/a b\0--headless\0PATH=/usr/bin\0HOME=/x\0"
    )
    assert process_args.parse_procargs2(raw) == b"Chrome\0--user-data-dir=/tmp/a b\0--headless\0"


async def test_a_move_refused_while_the_chrome_winds_down_waits_for_it(tmp_path, monkeypatch):
    """Windows: the dead holder's Chrome let go of ``lockfile``, but a helper
    process of it still has a file open in the folder for a moment, and the
    folder cannot be renamed until it is gone (WinError 5)."""
    calls = []
    real = os.rename

    def refused_twice(src, dst):
        calls.append(src)
        if len(calls) <= 2:
            raise PermissionError(13, "Access is denied")
        real(src, dst)

    monkeypatch.setattr(profile_release, "_MOVE_WAITS", True)
    monkeypatch.setattr(profile_release.os, "rename", refused_twice)
    (tmp_path / "s").mkdir()
    await profile_release.move(str(tmp_path / "s"), str(tmp_path / "grave"), timeout=5)
    assert len(calls) == 3
    assert (tmp_path / "grave").is_dir()


async def test_a_move_still_refused_at_the_timeout_raises(tmp_path, monkeypatch):
    def refused(src, dst):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(profile_release, "_MOVE_WAITS", True)
    monkeypatch.setattr(profile_release.os, "rename", refused)
    with pytest.raises(PermissionError):
        await profile_release.move(str(tmp_path / "s"), str(tmp_path / "grave"), timeout=0.2)


async def test_a_move_refused_on_posix_is_not_waited_for(tmp_path, monkeypatch):
    calls = []

    def refused(src, dst):
        calls.append(src)
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(profile_release, "_MOVE_WAITS", False)
    monkeypatch.setattr(profile_release.os, "rename", refused)
    with pytest.raises(PermissionError):
        await profile_release.move(str(tmp_path / "s"), str(tmp_path / "grave"), timeout=5)
    assert len(calls) == 1

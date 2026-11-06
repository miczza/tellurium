"""Windows launch path: dispatch, CRT fd-inheritance block, environment, discovery.

The construction of the CRT block, the environment block and the platform
dispatch are pinned everywhere; the real launch (a child that reads fd 3,
writes fd 4, prints its environment to the output it was given) runs on every
system with Python as the child, so on Windows it goes through ``CreateProcessW``.
"""

from __future__ import annotations

import concurrent.futures
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tellurium.browser import launch_windows, launcher, process
from tellurium.browser.launch_windows import (
    _CRT_FOPEN,
    _CRT_FPIPE,
    build_crt_inherit_block,
    build_environment_block,
)
from tellurium.browser.launcher import _find_chrome_candidates
from tellurium.browser.process import launch_chrome

# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def test_launch_chrome_uses_the_posix_launcher_on_linux(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        process,
        "launch_chrome_posix",
        lambda p, a, out, env: calls.append(("posix", p, a, out, env)) or ("P", 3, 4),
    )
    monkeypatch.setattr(
        process,
        "launch_chrome_windows",
        lambda *a: pytest.fail("windows launcher used on linux"),
    )
    assert launch_chrome("/usr/bin/chrome", ["--x"], 9, {"A": "1"}) == ("P", 3, 4)
    assert calls == [("posix", "/usr/bin/chrome", ["--x"], 9, {"A": "1"})]


def test_launch_chrome_uses_the_windows_launcher_on_win32(monkeypatch):
    """Output and environment reach the Windows launcher too."""
    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        process,
        "launch_chrome_windows",
        lambda p, a, out, env: calls.append(("win", p, a, out, env)) or ("W", 5, 6),
    )
    monkeypatch.setattr(
        process,
        "launch_chrome_posix",
        lambda *a: pytest.fail("posix launcher used on win32"),
    )
    assert launch_chrome(r"C:\chrome.exe", ["--y"], 9, {"A": "1"}) == ("W", 5, 6)
    assert calls == [("win", r"C:\chrome.exe", ["--y"], 9, {"A": "1"})]


@pytest.mark.skipif(sys.platform == "win32", reason="checks the POSIX side of the dispatch")
def test_windows_launcher_refuses_to_run_on_posix():
    with pytest.raises(RuntimeError, match="Windows-only"):
        launch_windows.launch_chrome_windows("chrome.exe", [])


def test_browser_launch_goes_through_the_dispatcher():
    """Chrome is spawned through the platform dispatcher, never the POSIX path directly."""
    from tellurium.browser import browser as browser_mod

    assert "launch_chrome(chrome_path, flags, output, env)" in Path(process.__file__).read_text()
    assert "launch_chrome_posix" not in Path(browser_mod.__file__).read_text()


# ---------------------------------------------------------------------------
# A real child: pipes on fds 3 and 4, output, environment
# ---------------------------------------------------------------------------

CHILD = r"""
import os, sys
sys.stdout.write("probe=" + ascii(os.environ.get("TELLURIUM_PROBE")) + "\n")
sys.stdout.flush()
data = b""
while not data.endswith(b"\0"):
    chunk = os.read(3, 100)
    if not chunk:
        break
    data += chunk
os.write(4, data.upper())
"""


def test_the_child_gets_the_pipes_the_output_and_the_environment(tmp_path):
    """What Chrome needs from the launcher, checked on a Python child: it reads
    fd 3 and writes fd 4, prints to the output it was given, sees the environment."""
    log = tmp_path / "child.log"
    env = {**os.environ, "TELLURIUM_PROBE": "caf\u00e9 \U0001f600 ok"}
    with open(log, "ab") as out:
        child, write_fd, read_fd = launch_chrome(sys.executable, ["-c", CHILD], out.fileno(), env)
    try:
        os.write(write_fd, b"ping\0")
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            reply = pool.submit(os.read, read_fd, 100).result(timeout=30)
        assert reply == b"PING\0"
        assert child.wait(timeout=30) == 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        os.close(write_fd)
        os.close(read_fd)
    assert "probe='caf\\xe9 \\U0001f600 ok'" in log.read_text()


def test_a_killed_child_is_reaped_with_its_exit_code(tmp_path):
    child, write_fd, read_fd = launch_chrome(sys.executable, ["-c", "import time; time.sleep(60)"])
    try:
        assert child.poll() is None
        child.kill()
        assert child.wait(timeout=30) != 0
        assert child.poll() == child.returncode
        child.kill()  # once it exited: nothing to do, no error
    finally:
        os.close(write_fd)
        os.close(read_fd)


# ---------------------------------------------------------------------------
# Environment block
# ---------------------------------------------------------------------------


def test_the_environment_block_is_sorted_without_regard_to_case():
    block = build_environment_block({"b": "2", "A": "1", "=C:": "C:\\x", "c": "\u00e9"})
    assert block == "=C:=C:\\x\0A=1\0b=2\0c=\u00e9\0\0"


def test_names_that_differ_only_in_case_are_one_variable():
    assert build_environment_block({"Path": "a", "PATH": "b"}) == "PATH=b\0\0"


def test_an_empty_environment_is_still_terminated():
    assert build_environment_block({}) == "\0"


@pytest.mark.parametrize("env", [{"": "x"}, {"A=B": "x"}, {"A\0": "x"}, {"A": "x\0y"}])
def test_an_invalid_environment_is_refused(env):
    with pytest.raises(ValueError):
        build_environment_block(env)


# ---------------------------------------------------------------------------
# CRT lpReserved2 block
# ---------------------------------------------------------------------------


def test_crt_block_layout_count_flags_handles():
    block = build_crt_inherit_block([None, None, None, 0x11, 0x22], handle_size=8)
    assert int.from_bytes(block[:4], "little") == 5
    flags = block[4:9]
    assert list(flags) == [0, 0, 0, _CRT_FOPEN | _CRT_FPIPE, _CRT_FOPEN | _CRT_FPIPE]
    handles = block[9:]
    assert len(handles) == 5 * 8
    assert int.from_bytes(handles[3 * 8 : 4 * 8], "little") == 0x11
    assert int.from_bytes(handles[4 * 8 : 5 * 8], "little") == 0x22


def test_crt_block_marks_unused_slots_invalid():
    block = build_crt_inherit_block([None], handle_size=8)
    assert block[4] == 0
    assert int.from_bytes(block[5:13], "little") == 0xFFFFFFFFFFFFFFFF


def test_crt_block_supports_32_bit_handles():
    block = build_crt_inherit_block([None, 0x7F], handle_size=4)
    assert len(block) == 4 + 2 + 2 * 4
    assert int.from_bytes(block[6:10], "little") == 0xFFFFFFFF
    assert int.from_bytes(block[10:14], "little") == 0x7F


def test_chrome_reads_fd3_and_writes_fd4():
    """The pipe protocol is positional: fd 3 in, fd 4 out — order matters."""
    block = build_crt_inherit_block([None, None, None, 0xAA, 0xBB], handle_size=8)
    handles = block[4 + 5 :]
    assert int.from_bytes(handles[3 * 8 : 4 * 8], "little") == 0xAA  # chrome reads
    assert int.from_bytes(handles[4 * 8 : 5 * 8], "little") == 0xBB  # chrome writes


def test_remote_debugging_pipe_flag_is_in_the_base_flags():
    assert "--remote-debugging-pipe" in launcher.BASE_FLAGS


def test_windows_command_line_quotes_paths_with_spaces():
    cmd = subprocess.list2cmdline(
        [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "--remote-debugging-pipe",
        ]
    )
    assert cmd.startswith('"C:\\Program Files\\')
    assert cmd.endswith("--remote-debugging-pipe")


# ---------------------------------------------------------------------------
# Binary discovery on Windows
# ---------------------------------------------------------------------------


def test_find_chrome_candidates_scans_the_standard_windows_paths(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(launcher, "_find_cft_managed", lambda: [])
    env = {
        "PROGRAMFILES": r"C:\Program Files",
        "PROGRAMFILES(X86)": r"C:\Program Files (x86)",
        "LOCALAPPDATA": r"C:\Users\u\AppData\Local",
    }
    monkeypatch.setattr(launcher.os, "environ", env)

    # pathlib joins with "/" when the tests run on POSIX, so compare on a
    # separator-insensitive form of the path.
    def _norm(path: str) -> str:
        return str(path).replace("/", "\\")

    found = {
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Users\u\AppData\Local\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    }
    with patch.object(Path, "is_file", lambda self: _norm(self) in found):
        candidates = _find_chrome_candidates()

    paths = {_norm(p) for p, _ in candidates}
    assert found <= paths
    kinds = [k for _, k in candidates]
    assert "chrome" in kinds and "edge" in kinds


def test_windows_discovery_ignores_empty_environment_entries(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(launcher, "_find_cft_managed", lambda: [])
    monkeypatch.setattr(launcher.os, "environ", {"LOCALAPPDATA": ""})
    with patch.object(Path, "is_file", lambda self: False):
        assert _find_chrome_candidates() == []


# ---------------------------------------------------------------------------
# Transport factory
# ---------------------------------------------------------------------------


def test_create_transport_picks_the_windows_pipe_on_win32(monkeypatch):
    import tellurium.cdp.transport as transport_pkg
    from tellurium.cdp.transport._pipe_win import PipeWindowsTransport

    monkeypatch.setattr(transport_pkg.sys, "platform", "win32")
    transport = transport_pkg.create_transport(7, 8)
    assert isinstance(transport, PipeWindowsTransport)
    assert (transport._read_fd, transport._write_fd) == (7, 8)


@pytest.mark.skipif(sys.platform == "win32", reason="checks the POSIX side of the dispatch")
def test_create_transport_picks_the_posix_pipe_elsewhere():
    from tellurium.cdp.transport import create_transport
    from tellurium.cdp.transport._pipe_posix import PipePosixTransport

    assert isinstance(create_transport(7, 8), PipePosixTransport)


def test_moved_spawn_functions_keep_their_old_import_path():
    from tellurium.browser.launcher import build_crt_inherit_block as old_block
    from tellurium.browser.launcher import launch_chrome as old_dispatch
    from tellurium.browser.launcher import launch_chrome_posix as old_posix
    from tellurium.browser.launcher import launch_chrome_windows as old_windows

    assert old_dispatch is process.launch_chrome
    assert old_posix is process.launch_chrome_posix
    assert old_windows is launch_windows.launch_chrome_windows
    assert old_block is build_crt_inherit_block


# ---------------------------------------------------------------------------
# WindowsProcess: one handle, polled from the loop and waited on in a thread
# ---------------------------------------------------------------------------


class _FakeWinapi:
    """``_winapi`` for one process handle: refuses a closed or doubly closed one."""

    def __init__(self) -> None:
        import threading

        self.exited = threading.Event()
        self.closed: list[int] = []
        self.terminated = 0

    def _check(self, handle):
        if handle is None or handle in self.closed:
            raise OSError(6, "The handle is invalid")

    def WaitForSingleObject(self, handle, ms):  # noqa: N802 (the API's name)
        import time

        self._check(handle)
        if self.exited.wait(None if ms == launch_windows._INFINITE else ms / 1000):
            if ms == launch_windows._INFINITE:
                time.sleep(0.2)  # the waiting thread wakes up late
            return launch_windows._WAIT_OBJECT_0
        return 0x102  # WAIT_TIMEOUT

    def GetExitCodeProcess(self, handle):  # noqa: N802
        self._check(handle)
        return 0

    def CloseHandle(self, handle):  # noqa: N802
        self._check(handle)
        self.closed.append(handle)

    def TerminateProcess(self, handle, code):  # noqa: N802
        self._check(handle)
        self.terminated += 1
        self.exited.set()


def test_a_poll_racing_a_wait_closes_the_handle_once(monkeypatch):
    fake = _FakeWinapi()
    monkeypatch.setitem(sys.modules, "_winapi", fake)
    proc = launch_windows.WindowsProcess(handle=1234, pid=99)
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(proc.wait)
        assert proc.poll() is None
        fake.exited.set()
        assert proc.poll() == 0  # the loop sees the exit first
        assert waiting.result(5) == 0
    assert fake.closed == [1234]
    proc.terminate()  # after the exit: nothing to do, no closed handle touched
    assert fake.terminated == 0


def test_terminate_while_a_thread_waits(monkeypatch):
    fake = _FakeWinapi()
    monkeypatch.setitem(sys.modules, "_winapi", fake)
    proc = launch_windows.WindowsProcess(handle=77, pid=5)
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(proc.wait, 10)
        proc.kill()
        assert waiting.result(5) == 0
    assert fake.terminated == 1 and fake.closed == [77]

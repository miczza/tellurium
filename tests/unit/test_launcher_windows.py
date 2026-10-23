"""Windows launch path: dispatch, CRT fd-inheritance block, binary discovery.

None of this is exercised against a real chrome.exe — Tellurium's CI is POSIX
only — so the tests pin the *construction* of the handle block, the command
line and the platform dispatch, which is what a Windows regression would break
first.  See launch_chrome_windows()'s "untested on real Windows" note.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tellurium.browser import launcher, process
from tellurium.browser.launcher import (
    _CRT_FOPEN,
    _CRT_FPIPE,
    _find_chrome_candidates,
    build_crt_inherit_block,
)
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
        lambda p, a, out: calls.append(("posix", p, a)) or ("P", 3, 4),
    )
    monkeypatch.setattr(
        process,
        "launch_chrome_windows",
        lambda p, a: pytest.fail("windows launcher used on linux"),
    )
    assert launch_chrome("/usr/bin/chrome", ["--x"]) == ("P", 3, 4)
    assert calls == [("posix", "/usr/bin/chrome", ["--x"])]


def test_launch_chrome_uses_the_windows_launcher_on_win32(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        process, "launch_chrome_windows", lambda p, a: calls.append(("win", p, a)) or ("W", 5, 6)
    )
    monkeypatch.setattr(
        process,
        "launch_chrome_posix",
        lambda p, a, out: pytest.fail("posix launcher used on win32"),
    )
    assert launch_chrome(r"C:\chrome.exe", ["--y"]) == ("W", 5, 6)
    assert calls == [("win", r"C:\chrome.exe", ["--y"])]


def test_windows_launcher_refuses_to_run_on_posix():
    with pytest.raises(RuntimeError, match="Windows-only"):
        launcher.launch_chrome_windows("chrome.exe", [])


def test_browser_launch_goes_through_the_dispatcher():
    """Chrome is spawned through the platform dispatcher, never the POSIX path directly."""
    from tellurium.browser import browser as browser_mod

    assert "launch_chrome(chrome_path, flags, output)" in Path(process.__file__).read_text()
    assert "launch_chrome_posix" not in Path(browser_mod.__file__).read_text()


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
    """_pipe_win refuses to import off-Windows, so stub the module."""
    import types

    import tellurium.cdp.transport as transport_pkg

    stub = types.ModuleType("tellurium.cdp.transport._pipe_win")

    class PipeWindowsTransport:
        def __init__(self, read_fd, write_fd):
            self.read_fd, self.write_fd = read_fd, write_fd

    stub.PipeWindowsTransport = PipeWindowsTransport
    monkeypatch.setitem(sys.modules, "tellurium.cdp.transport._pipe_win", stub)
    monkeypatch.setattr(transport_pkg.sys, "platform", "win32")

    transport = transport_pkg.create_transport(7, 8)
    assert isinstance(transport, PipeWindowsTransport)
    assert (transport.read_fd, transport.write_fd) == (7, 8)


def test_create_transport_picks_the_posix_pipe_elsewhere():
    from tellurium.cdp.transport import create_transport
    from tellurium.cdp.transport._pipe_posix import PipePosixTransport

    assert isinstance(create_transport(7, 8), PipePosixTransport)


def test_windows_transport_exposes_start():
    """browser.py awaits transport.start() on every platform."""
    source = (
        Path(launcher.__file__).parent.parent.joinpath("cdp/transport/_pipe_win.py").read_text()
    )
    assert "async def start(self)" in source

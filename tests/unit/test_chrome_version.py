"""Chrome's version, read without starting a browser where the system allows it.

``chrome --version`` on Linux and macOS; on Windows (where ``chrome.exe
--version`` opens a window and never exits) the install layout, then the
file's ``VERSIONINFO``; on macOS the bundle's ``Info.plist`` when the flag is
silent.
"""

from __future__ import annotations

import asyncio
import plistlib
import struct
import subprocess
import sys

import pytest

from tellurium.browser import chrome_version
from tellurium.browser.chrome_version import detect_chrome_version


def _no_subprocess(*_a, **_kw):
    pytest.fail("ran the executable to read its version")


# --------------------------------------------------------------------------- #
# --version (Linux, macOS)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("platform", ["linux", "darwin"])
@pytest.mark.parametrize(
    "output, expected",
    [
        (b"Google Chrome 146.0.7680.188\n", (146, 0, 7680, 188)),
        (b"Chromium 145.0.7600.100 snap\n", (145, 0, 7600, 100)),
    ],
)
def test_the_version_flag_is_read_on_posix(monkeypatch, platform, output, expected):
    monkeypatch.setattr(chrome_version.sys, "platform", platform)
    monkeypatch.setattr(chrome_version.subprocess, "check_output", lambda *a, **kw: output)
    assert detect_chrome_version("/usr/bin/chrome") == expected


def test_a_failing_version_flag_gives_none_on_linux(monkeypatch):
    def fail(*_a, **_kw):
        raise subprocess.TimeoutExpired("chrome", 10)

    monkeypatch.setattr(chrome_version.sys, "platform", "linux")
    monkeypatch.setattr(chrome_version.subprocess, "check_output", fail)
    assert detect_chrome_version("/usr/bin/chrome") is None


def test_a_silent_version_flag_gives_none_on_linux(monkeypatch):
    monkeypatch.setattr(chrome_version.sys, "platform", "linux")
    monkeypatch.setattr(chrome_version.subprocess, "check_output", lambda *a, **kw: b"")
    assert detect_chrome_version("/usr/bin/chrome") is None


# --------------------------------------------------------------------------- #
# Info.plist (macOS)
# --------------------------------------------------------------------------- #


def _bundle(tmp_path, version: object = "157.0.7400.12"):
    contents = tmp_path / "Google Chrome.app" / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    executable = contents / "MacOS" / "Google Chrome"
    executable.write_text("")
    info = {"CFBundleIdentifier": "com.google.Chrome"}
    if version is not None:
        info["CFBundleShortVersionString"] = version
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    return executable


def test_on_macos_a_silent_flag_falls_back_to_the_bundle_plist(tmp_path, monkeypatch):
    executable = _bundle(tmp_path)
    monkeypatch.setattr(chrome_version.sys, "platform", "darwin")
    monkeypatch.setattr(chrome_version.subprocess, "check_output", lambda *a, **kw: b"")
    assert detect_chrome_version(str(executable)) == (157, 0, 7400, 12)


def test_on_macos_the_flag_wins_over_the_plist(tmp_path, monkeypatch):
    executable = _bundle(tmp_path, "1.0.0.0")
    monkeypatch.setattr(chrome_version.sys, "platform", "darwin")
    monkeypatch.setattr(
        chrome_version.subprocess, "check_output", lambda *a, **kw: b"Google Chrome 157.0.1.2"
    )
    assert detect_chrome_version(str(executable)) == (157, 0, 1, 2)


@pytest.mark.parametrize("version", [None, "157.0", 157, "abc"])
def test_a_plist_without_a_full_version_gives_none(tmp_path, monkeypatch, version):
    executable = _bundle(tmp_path, version)
    monkeypatch.setattr(chrome_version.sys, "platform", "darwin")
    monkeypatch.setattr(chrome_version.subprocess, "check_output", lambda *a, **kw: b"")
    assert detect_chrome_version(str(executable)) is None


def test_an_executable_outside_a_bundle_has_no_plist(tmp_path, monkeypatch):
    (tmp_path / "chrome").write_text("")
    monkeypatch.setattr(chrome_version.sys, "platform", "darwin")
    monkeypatch.setattr(chrome_version.subprocess, "check_output", lambda *a, **kw: b"")
    assert detect_chrome_version(str(tmp_path / "chrome")) is None


def test_a_corrupt_plist_gives_none(tmp_path, monkeypatch):
    executable = _bundle(tmp_path)
    (executable.parent.parent / "Info.plist").write_bytes(b"\0not a plist")
    monkeypatch.setattr(chrome_version.sys, "platform", "darwin")
    monkeypatch.setattr(chrome_version.subprocess, "check_output", lambda *a, **kw: b"")
    assert detect_chrome_version(str(executable)) is None


# --------------------------------------------------------------------------- #
# Windows: install layout, then VERSIONINFO; never the executable itself
# --------------------------------------------------------------------------- #


def test_windows_version_comes_from_the_install_layout(tmp_path, monkeypatch):
    app = tmp_path / "Application"
    for name in ("130.0.6723.70", "131.0.6778.86", "SetupMetrics"):
        (app / name).mkdir(parents=True)
    (app / "chrome.exe").write_text("")
    monkeypatch.setattr(chrome_version.sys, "platform", "win32")
    monkeypatch.setattr(chrome_version.subprocess, "check_output", _no_subprocess)
    monkeypatch.setattr(chrome_version, "_from_version_resource", lambda _p: pytest.fail())
    assert detect_chrome_version(str(app / "chrome.exe")) == (131, 0, 6778, 86)


def test_windows_without_a_version_dir_reads_the_version_resource(tmp_path, monkeypatch):
    (tmp_path / "chrome.exe").write_text("")
    monkeypatch.setattr(chrome_version.sys, "platform", "win32")
    monkeypatch.setattr(chrome_version.subprocess, "check_output", _no_subprocess)
    monkeypatch.setattr(chrome_version, "_from_version_resource", lambda _p: (150, 0, 1, 2))
    assert detect_chrome_version(str(tmp_path / "chrome.exe")) == (150, 0, 1, 2)


def test_windows_without_any_source_gives_none(tmp_path, monkeypatch):
    (tmp_path / "chrome.exe").write_text("")
    monkeypatch.setattr(chrome_version.sys, "platform", "win32")
    monkeypatch.setattr(chrome_version.subprocess, "check_output", _no_subprocess)
    monkeypatch.setattr(chrome_version, "_from_version_resource", lambda _p: None)
    assert detect_chrome_version(str(tmp_path / "chrome.exe")) is None


def _fixed_file_info(ms: int, ls: int, signature: int = 0xFEEF04BD) -> bytes:
    """A VS_FIXEDFILEINFO: signature, struct version, file version MS/LS, then 9 more DWORDs."""
    return struct.pack("<13I", signature, 0x10000, ms, ls, *([0] * 9))


def test_the_fixed_file_info_gives_the_four_parts():
    raw = _fixed_file_info((157 << 16) | 0, (7400 << 16) | 12)
    assert chrome_version._version_from_fixed_info(raw) == (157, 0, 7400, 12)


@pytest.mark.parametrize(
    "raw",
    [
        _fixed_file_info(157 << 16, 12, signature=0x12345678),  # not a VS_FIXEDFILEINFO
        _fixed_file_info(0, 0),  # no version at all
        b"\xbd\x04\xef\xfe",  # truncated
    ],
)
def test_a_bad_fixed_file_info_gives_none(raw):
    assert chrome_version._version_from_fixed_info(raw) is None


@pytest.mark.skipif(sys.platform != "win32", reason="VERSIONINFO is a Windows resource")
def test_the_version_resource_of_a_real_executable_is_read():
    """python.exe carries a VERSIONINFO like chrome.exe: read it through the Win32 API."""
    found = chrome_version._from_version_resource(sys.executable)
    assert found is not None and found[:2] == sys.version_info[:2]


@pytest.mark.skipif(sys.platform == "win32", reason="the Win32 API exists only on Windows")
def test_the_version_resource_is_none_off_windows(tmp_path):
    (tmp_path / "chrome.exe").write_text("")
    assert chrome_version._from_version_resource(str(tmp_path / "chrome.exe")) is None


# --------------------------------------------------------------------------- #
# Callers read it off the event loop
# --------------------------------------------------------------------------- #


async def test_find_chrome_reads_the_version_off_the_loop(monkeypatch):
    """With stealth, find_chrome() checks branded Chrome's version: in a thread."""
    from tellurium.browser import launcher

    loop_thread = []

    def probe(path):
        try:
            asyncio.get_running_loop()
            loop_thread.append(True)
        except RuntimeError:
            loop_thread.append(False)
        return (150, 0, 0, 0)

    monkeypatch.setattr(launcher, "_find_chrome_candidates", lambda: [("/x/chrome", "chrome")])
    monkeypatch.setattr(launcher, "detect_chrome_version", probe)
    assert await launcher.find_chrome(stealth=True) == "/x/chrome"
    assert loop_thread == [False]

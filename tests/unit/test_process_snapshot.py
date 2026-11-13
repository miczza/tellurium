"""The process snapshot of the hang probe: never root, never a process left behind,
something even on a stalled Windows runner."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time

import pytest

from tests import process_snapshot

#: A child that starts a grandchild, which writes *path* after 3 s if still alive.
_FAMILY = (
    "import subprocess, sys, time;"
    "subprocess.Popen([sys.executable, '-c',"
    " 'import sys, time; time.sleep(3); open(sys.argv[1], \"w\").close()', sys.argv[1]]);"
    "time.sleep(60)"
)


def test_a_command_past_its_deadline_is_ended_with_every_process_it_started(tmp_path):
    alive = tmp_path / "grandchild-alive"
    started = time.monotonic()
    text, ok = process_snapshot._run([sys.executable, "-c", _FAMILY, str(alive)], timeout=1.0)
    assert not ok and "timed out" in text
    assert time.monotonic() - started < 15
    time.sleep(4)
    assert not alive.exists(), "the grandchild outlived the deadline"


def test_no_command_runs_as_root_unless_the_ci_asks(monkeypatch):
    monkeypatch.delenv(process_snapshot.SUDO_ENV, raising=False)
    monkeypatch.setattr(process_snapshot.shutil, "which", lambda name: "/usr/bin/sudo")
    assert process_snapshot._sudo() == []


def test_a_windows_snapshot_that_times_out_falls_back_to_a_light_list(monkeypatch):
    calls: list[list[str]] = []

    def run(cmd, timeout=process_snapshot.COMMAND_TIMEOUT):
        calls.append(cmd)
        if cmd[0] == "powershell":
            return "(powershell timed out after 20s)", False
        return '"chrome.exe","4368","Console","1","165,000 K","Unknown"', True

    monkeypatch.setattr(process_snapshot, "_run", run)
    text = process_snapshot._windows(4368)
    assert [c[0] for c in calls] == ["powershell", "tasklist"]
    assert "powershell timed out" in text
    assert '"chrome.exe","4368"' in text


def test_each_process_says_when_it_was_born_from_the_send(tmp_path):
    """The birth of each process of the tree, in seconds from the stalled send:
    whether Chrome's new renderer was born late (R4-B)."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        time.sleep(0.5)
        since = time.time() - 30.0  # the send, 30 s before the snapshot
        text = process_snapshot.snapshot(child.pid, since=since)
    finally:
        child.kill()
        child.wait(10)
    [born] = re.findall(rf"pid {child.pid} .*born=([+-][\d.]+)s", text)
    assert 25.0 < float(born) < 30.5, text


def test_a_snapshot_without_a_send_gives_the_utc_clock():
    text = process_snapshot.snapshot(os.getpid())
    assert re.search(rf"pid {os.getpid()} .*born=\d\d:\d\d:\d\d\.\d\d\dZ", text), text


def test_the_machine_view_names_the_load_of_the_whole_machine():
    text = process_snapshot.machine(since=time.time() - 5.0)
    assert text.strip()
    if sys.platform != "win32":
        assert "load average" in text
    else:  # a shadow copy probably froze a runner: its events, "(none)" included, are there
        assert "shadow copy events since" in text, text


def test_a_moment_of_the_machine_view_is_given_from_the_send_like_a_birth():
    text = process_snapshot.births("pid 7 x born@1000500\n  System volsnap at@999000 x", 1000.0)
    assert text == "pid 7 x born=+0.50s\n  System volsnap at=-1.00s x"


class _RootCommand:
    """A command run as root past its deadline: deaf to signals, ``kill`` refused."""

    pid = 2**22 - 1  # no such process group: ``killpg`` finds nothing

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired("sudo", timeout)

    def kill(self):
        raise PermissionError(1, "Operation not permitted")


@pytest.mark.skipif(sys.platform == "win32", reason="the POSIX path of the process group")
def test_a_command_that_refuses_to_be_ended_does_not_end_the_snapshot(monkeypatch):
    monkeypatch.setattr(process_snapshot.time, "sleep", lambda s: None)
    process_snapshot._end_tree(_RootCommand())  # no PermissionError

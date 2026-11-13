"""The process snapshot of the hang probe: never root, never a process left behind,
something even on a stalled Windows runner."""

from __future__ import annotations

import sys
import time

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

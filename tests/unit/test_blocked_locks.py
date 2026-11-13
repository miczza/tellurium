"""Who holds the lock that a stuck macOS process waits for: the probe looks
only when ``sample`` shows a thread parked on a read-write lock."""

from __future__ import annotations

import threading

import pytest

from tests import blocked_locks, hang_probe, process_snapshot

_PARKED = """Call graph:
    1752 Thread_24581   DispatchQueue_1: com.apple.main-thread  (serial)
    + 1752 ChromeMain  (in Google Chrome Framework) + 28793800  [0x121b5a768]
    +   1752 _pthread_rwlock_lock_slow  (in libsystem_pthread.dylib) + 688  [0x187274420]
    +     1752 _pthread_rwlock_lock_wait  (in libsystem_pthread.dylib) + 84  [0x1872762b0]
    +       1752 __psynch_rw_wrlock  (in libsystem_kernel.dylib) + 8  [0x18723afe4]
"""
_IDLE = """Call graph:
    1752 Thread_24581   DispatchQueue_1: com.apple.main-thread  (serial)
    + 1752 mach_msg2_trap  (in libsystem_kernel.dylib) + 8  [0x187235c34]
"""


def test_no_thread_on_a_rwlock_runs_nothing(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(blocked_locks, "_run", lambda cmd: calls.append(cmd))
    assert blocked_locks.rwlocks(4771, _IDLE) == ""
    assert calls == []


def test_a_thread_on_a_rwlock_attaches_lldb_and_detaches(monkeypatch):
    calls: list[list[str]] = []

    def run(cmd):
        calls.append(cmd)
        return "thread 24581 waits to write rwlock 0x6000 held for writing by: nobody", True

    monkeypatch.setattr(blocked_locks, "_run", run)
    monkeypatch.setattr(blocked_locks, "_sudo", lambda: ["sudo", "-n"])
    text = blocked_locks.rwlocks(4771, _PARKED)
    [cmd] = calls
    assert cmd[:3] == ["sudo", "-n", "lldb"]
    assert cmd[cmd.index("-p") + 1] == "4771" and "--batch" in cmd
    assert cmd[-2:] == ["-o", "process detach"]
    assert text.startswith("read-write locks waited on (lldb):")
    assert "held for writing by: nobody" in text


def test_the_lldb_script_finds_the_lock_and_its_owner_by_thread_id():
    script = blocked_locks.LLDB_SCRIPT
    compile(script, "lock_owner.py", "exec")  # lldb's own Python runs it
    # a lock used once is signed 'RWLK'; one never used yet, by its static initialiser
    assert set(blocked_locks.RWLOCK_SIGS) == {0x52574C4B, 0x2DA8B3B4}
    assert all(hex(sig) in script for sig in blocked_locks.RWLOCK_SIGS)
    assert "lcntval" in script  # the sequence words are decoded
    assert "__psynch_rw_" in script and "GetThreadID" in script


def test_the_macos_snapshot_is_the_tree_and_the_sample_without_lldb(monkeypatch):
    """lldb is the hang probe's to start, after the sample is on disk."""
    ps = "4771 1 S< 0.0 192784 00:09 /Applications/Google Chrome --type=x\n"
    monkeypatch.setattr(process_snapshot, "_run", lambda cmd, timeout=0: (ps, True))
    monkeypatch.setattr(process_snapshot, "_sample", lambda pid: _PARKED)
    monkeypatch.setattr(blocked_locks, "_run", lambda cmd: pytest.fail("lldb attached"))
    text = process_snapshot._macos(4771)
    assert "sample of 4771" in text and "__psynch_rw_wrlock" in text
    assert "read-write locks waited on" not in text


def test_lldb_that_fails_is_a_line_not_an_error(monkeypatch):
    def run(cmd):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(blocked_locks, "_run", run)
    monkeypatch.setattr(blocked_locks, "_sudo", lambda: [])
    text = blocked_locks.rwlocks(4771, _PARKED)
    assert text.startswith("read-write locks waited on (lldb):")
    assert "lldb failed: PermissionError" in text


def _parked_snapshot(pid):
    return f"pid {pid} Google Chrome state=S\nsample of {pid}, 3 s:\n{_PARKED}"


def test_the_sample_is_in_the_report_before_lldb_and_outlives_its_failure(tmp_path, monkeypatch):
    path = tmp_path / "report.txt"
    on_disk: list[str] = []

    def rwlocks(pid, sample):
        on_disk.append(path.read_text())
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(hang_probe, "snapshot", _parked_snapshot)
    monkeypatch.setattr(blocked_locks, "rwlocks", rwlocks)
    assert hang_probe._snapshot_into(path, 4771, threading.Event()) is True
    [before] = on_disk
    assert "__psynch_rw_wrlock" in before  # the sample was written before lldb started
    text = path.read_text()
    assert "__psynch_rw_wrlock" in text
    assert "lldb failed: PermissionError" in text


def test_lldb_is_not_attached_once_the_command_has_its_answer(tmp_path, monkeypatch):
    """lldb stops all of Chrome for ~10 s: not for a command that came back."""
    path = tmp_path / "report.txt"
    answered = threading.Event()
    answered.set()
    monkeypatch.setattr(hang_probe, "snapshot", _parked_snapshot)
    monkeypatch.setattr(blocked_locks, "rwlocks", lambda pid, s: pytest.fail("lldb attached"))
    assert hang_probe._snapshot_into(path, 4771, answered) is False
    text = path.read_text()
    assert "__psynch_rw_wrlock" in text
    assert "not looked at: the command was answered" in text


def test_no_thread_on_a_rwlock_leaves_the_report_without_a_lock_line(tmp_path, monkeypatch):
    path = tmp_path / "report.txt"
    monkeypatch.setattr(hang_probe, "snapshot", lambda pid: f"sample of {pid}, 3 s:\n{_IDLE}")
    assert hang_probe._snapshot_into(path, 4771, threading.Event()) is False
    assert "read-write locks" not in path.read_text()

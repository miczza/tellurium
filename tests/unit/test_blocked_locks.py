"""Who holds the lock that a stuck macOS process waits for: the probe looks
only when ``sample`` shows a thread parked on a read-write lock."""

from __future__ import annotations

from tests import blocked_locks, process_snapshot

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
    assert hex(blocked_locks.RWLOCK_SIG) in script
    assert "__psynch_rw_" in script and "GetThreadID" in script


def test_the_macos_snapshot_adds_the_locks_after_the_sample(monkeypatch):
    ps = "4771 1 S< 0.0 192784 00:09 /Applications/Google Chrome --type=x\n"
    monkeypatch.setattr(process_snapshot, "_run", lambda cmd, timeout=0: (ps, True))
    monkeypatch.setattr(process_snapshot, "_sample", lambda pid: _PARKED)
    seen: list[tuple[int, str]] = []

    def rwlocks(pid, sample):
        seen.append((pid, sample))
        return "read-write locks waited on (lldb):\n  owner"

    monkeypatch.setattr(process_snapshot.blocked_locks, "rwlocks", rwlocks)
    text = process_snapshot._macos(4771)
    assert seen == [(4771, _PARKED)]
    assert text.index("sample of 4771") < text.index("read-write locks waited on")

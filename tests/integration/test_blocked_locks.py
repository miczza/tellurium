"""The hang probe names who holds a read-write lock that threads wait for,
against a real process on macOS: a writer holds a ``pthread_rwlock_t`` while a
second writer waits for it, as Chrome's threads were seen parked (run
43001946271). The sample is in the report before lldb attaches, and lldb
attaches only while the watched command has no answer. On the CI lldb runs
as root, like ``sample``."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time

import pytest

from tests import hang_probe

#: Holds a rwlock for writing in one thread, waits for it in another; prints
#: both thread ids once the waiter is about to block.
_HOLDER = r"""
import ctypes, sys, threading, time
libc = ctypes.CDLL(None)
lock = ctypes.create_string_buffer(256)
assert libc.pthread_rwlock_init(lock, None) == 0
held = threading.Event()
ids = {}

def holder():
    ids["holder"] = threading.get_native_id()
    libc.pthread_rwlock_wrlock(lock)
    held.set()
    time.sleep(600)

def waiter():
    ids["waiter"] = threading.get_native_id()
    held.wait()
    print(ids["holder"], ids["waiter"], flush=True)
    libc.pthread_rwlock_wrlock(lock)

threading.Thread(target=holder, daemon=True).start()
threading.Thread(target=waiter, daemon=True).start()
time.sleep(600)
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="sample and lldb are macOS's")
def test_a_writer_waiting_on_a_rwlock_names_the_writer_that_holds_it(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", _HOLDER], stdout=subprocess.PIPE, text=True)
    try:
        holder, waiter = map(int, child.stdout.readline().split())
        time.sleep(1.0)  # the waiter parks in the kernel
        report = tmp_path / "report.txt"
        assert hang_probe._snapshot_into(report, child.pid, threading.Event()) is True
    finally:
        child.kill()
        child.wait(10)
    text = report.read_text()
    print(text)
    sample, locks = text.split("--- read-write locks waited on (lldb):", 1)
    assert "__psynch_rw_wrlock" in sample  # in the report before lldb attached
    assert f"thread {waiter} " in locks
    assert f"held for writing by: thread {holder} " in locks


@pytest.mark.skipif(sys.platform != "darwin", reason="sample and lldb are macOS's")
def test_a_command_answered_before_the_sample_ends_leaves_the_lock_alone(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", _HOLDER], stdout=subprocess.PIPE, text=True)
    answered = threading.Event()
    answered.set()
    try:
        child.stdout.readline()
        time.sleep(1.0)
        report = tmp_path / "report.txt"
        assert hang_probe._snapshot_into(report, child.pid, answered) is False
    finally:
        child.kill()
        child.wait(10)
    text = report.read_text()
    assert "__psynch_rw_wrlock" in text
    assert "not looked at: the command was answered" in text
    assert "(lldb)" not in text


@pytest.mark.skipif(sys.platform != "darwin", reason="sample and lldb are macOS's")
async def test_lldb_attaches_to_the_hardened_chrome_and_the_report_says_it_answers_after(
    browser, monkeypatch, tmp_path
):
    """The probe's path on a real Chrome: its sample in the report, lldb
    attached (a parked thread is made up, Chrome's own are rarely parked),
    then whether Chrome answers once lldb has let it go."""
    pid = browser._proc.process.pid
    parked = "    + 1 __psynch_rw_wrlock  (in libsystem_kernel.dylib) + 8  [0x1]"
    real = hang_probe.snapshot
    monkeypatch.setattr(hang_probe, "snapshot", lambda p: f"{real(p)}\n{parked}")
    report, unanswered = tmp_path / "report.txt", threading.Event()
    assert await asyncio.to_thread(hang_probe._snapshot_into, report, pid, unanswered)
    await hang_probe._after_detach(report, browser._router.root, "Page.navigate", unanswered)
    text = report.read_text()
    print(text)
    sample, locks = text.split("--- read-write locks waited on (lldb):", 1)
    assert "Call graph" in sample or "Thread_" in sample
    assert f"attached to {pid}, " in locks
    after = locks.split("--- does Chrome answer after lldb detached?", 1)[1]
    assert "root Browser.getVersion: ok in" in after
    assert "the watched Page.navigate: not answered" in after

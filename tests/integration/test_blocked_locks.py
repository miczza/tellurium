"""The hang probe names who holds a read-write lock that threads wait for,
against a real process on macOS: a writer holds a ``pthread_rwlock_t`` while a
second writer waits for it, as Chrome's threads were seen parked (run
43001946271). On the CI lldb runs as root, like ``sample``."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time

import pytest

from tests import blocked_locks, process_snapshot

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
def test_a_writer_waiting_on_a_rwlock_names_the_writer_that_holds_it():
    child = subprocess.Popen([sys.executable, "-c", _HOLDER], stdout=subprocess.PIPE, text=True)
    try:
        holder, waiter = map(int, child.stdout.readline().split())
        time.sleep(1.0)  # the waiter parks in the kernel
        text = process_snapshot.snapshot(child.pid)
    finally:
        child.kill()
        child.wait(10)
    print(text)
    assert "__psynch_rw_wrlock" in text
    assert "read-write locks waited on (lldb):" in text
    assert f"thread {waiter} " in text
    assert f"held for writing by: thread {holder} " in text


@pytest.mark.skipif(sys.platform != "darwin", reason="sample and lldb are macOS's")
async def test_lldb_attaches_to_the_hardened_chrome_and_leaves_it_running(browser):
    pid = browser._proc.process.pid
    parked = "    + 1 __psynch_rw_wrlock  (in libsystem_kernel.dylib) + 8  [0x1]"
    text = await asyncio.to_thread(blocked_locks.rwlocks, pid, parked)
    print(text)
    assert f"attached to {pid}, " in text
    assert await browser._router.root.send("Browser.getVersion")  # detached: it answers

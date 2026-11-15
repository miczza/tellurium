"""The processes of a Windows machine read in this process: no PowerShell to
start on a frozen runner (run 43496669198)."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time

import pytest

from tests import windows_processes as wp
from tests.process_freeze import frozen

_FILETIME_2026 = wp._EPOCH_TICKS + 1_790_000_000 * 10_000_000


def _entry(pid, parent, name, threads, born=_FILETIME_2026):
    """One process of a kernel buffer: its record, its threads, its name."""
    raw = name.encode("utf-16-le")
    size = ctypes.sizeof(wp._ProcessInfo) + len(threads) * ctypes.sizeof(wp._ThreadInfo)
    return pid, parent, raw, threads, born, size


def _buffer(entries):
    sizes = [e[5] + len(e[2]) + 8 for e in entries]
    buf = ctypes.create_string_buffer(sum(sizes))
    base, offset = ctypes.addressof(buf), 0
    for n, ((pid, parent, raw, threads, born, size), step) in enumerate(
        zip(entries, sizes, strict=True)
    ):
        info = wp._ProcessInfo.from_address(base + offset)
        info.next_entry_offset = step if n < len(entries) - 1 else 0
        info.number_of_threads = len(threads)
        info.create_time = born
        info.user_time = 15_000_000
        info.unique_process_id = pid
        info.inherited_from_unique_process_id = parent
        info.working_set_size = 50 << 20
        at = base + offset + size
        ctypes.memmove(at, raw, len(raw))
        info.image_name.buffer, info.image_name.length = at, len(raw)
        for i, (state, reason) in enumerate(threads):
            t_at = (
                base + offset + ctypes.sizeof(wp._ProcessInfo) + i * ctypes.sizeof(wp._ThreadInfo)
            )
            t = wp._ThreadInfo.from_address(t_at)
            t.unique_thread, t.thread_state, t.wait_reason = 100 + i, state, reason
        offset += step
    return buf


def test_a_kernel_buffer_gives_each_process_with_its_threads():
    buf = _buffer(
        [_entry(4, 0, "System", [(2, 0)]), _entry(812, 4, "chrome.exe", [(5, 5), (5, 12), (5, 6)])]
    )
    system, chrome = wp.parse(buf)
    assert (system.pid, system.name) == (4, "System")
    assert (chrome.pid, chrome.parent, chrome.name) == (812, 4, "chrome.exe")
    assert chrome.born == pytest.approx(1_790_000_000)
    assert chrome.cpu == pytest.approx(1.5)
    assert [t.group for t in chrome.threads] == [
        "Waiting/Suspended",
        "Waiting/Suspended",
        "Waiting/UserRequest",
    ]
    assert system.threads[0].group == "Running"


def test_an_unset_birth_is_none():
    assert wp.unix_time(0) is None


@pytest.mark.skipif(sys.platform != "win32", reason="asks the Windows kernel")
def test_the_kernel_lists_this_process_and_a_suspended_child():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        time.sleep(0.5)
        with frozen(child.pid):
            listed = {p.pid: p for p in wp.processes()}
    finally:
        child.kill()
        child.wait(10)
    me, it = listed[os.getpid()], listed[child.pid]
    assert it.parent == os.getpid()
    assert abs(it.born - time.time()) < 120
    assert me.threads and all(t.reason == "Suspended" for t in it.threads), it.threads


def _proc(pid, parent, name, born, *groups):
    threads = [
        wp.Thread(tid=pid * 10 + i, state=s, reason=r, cpu=0.5) for i, (s, r) in enumerate(groups)
    ]
    return wp.Process(pid, parent, name, born, cpu=1.0, working_set=64 << 20, threads=threads)


_MACHINE = [
    _proc(4, 0, "System", None, ("Running", "Executive")),
    _proc(900, 4, "chrome.exe", 1000.0, ("Waiting", "Suspended"), ("Waiting", "Suspended")),
    _proc(901, 900, "chrome.exe", 1002.5, ("Waiting", "UserRequest")),
    _proc(950, 4, "VSSVC.exe", 1001.0, ("Running", "Executive")),
]


def test_the_tree_of_a_process_groups_its_threads_like_get_process():
    text = wp.tree(900, _MACHINE)
    rows = text.splitlines()
    assert (
        rows[0] == "pid 900 chrome.exe cpu=1.0s ws=64MB born@1000000 threads: 2xWaiting/Suspended"
    )
    assert (
        rows[1]
        == "  pid 901 chrome.exe cpu=1.0s ws=64MB born@1002500 threads: 1xWaiting/UserRequest"
    )
    assert rows[2] == "threads of 900 (id state wait cpu):"
    assert rows[3] == "  9000 Waiting Suspended 0.5s"


def test_the_tree_of_a_process_gone_says_so():
    assert wp.tree(777, _MACHINE) == "no process 777"


def test_the_processes_born_since_a_moment_oldest_first():
    assert wp.born_since(1000.5, _MACHINE) == [
        "  pid 950 VSSVC.exe parent=4 born@1001000",
        "  pid 901 chrome.exe parent=900 born@1002500",
    ]

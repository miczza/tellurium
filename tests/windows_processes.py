"""Every process of a Windows machine, read in this process, for the hang probe.

On a runner frozen by a shadow copy even a new ``powershell`` (and the
``tasklist`` of the light list) did not start within 20 s (run 43496669198):
a stall left no snapshot at all. ``NtQuerySystemInformation`` (the call
``Get-Process`` makes itself) asks the kernel from inside the Python already
running: no process to start, nothing to read from the disk. It gives each
process with its parent, birth, CPU, memory and the state and wait reason of
each thread (``Suspended`` for a suspended one).

:func:`parse` reads the kernel's buffer on any system (the tests build one);
:func:`processes` asks the kernel, on Windows only.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass, field

#: ``SystemProcessInformation``: every process and its threads.
_SYSTEM_PROCESS_INFORMATION = 5
#: ``STATUS_INFO_LENGTH_MISMATCH``: the buffer was too small.
_TOO_SMALL = 0xC0000004
#: 100 ns ticks from 1601-01-01 (``FILETIME``) to the Unix epoch.
_EPOCH_TICKS = 116444736000000000
#: A buffer this much larger than the kernel asked for: processes are born meanwhile.
_SLACK = 1 << 16
#: How many times the kernel gets asked for a larger buffer.
_TRIES = 5

#: ``KTHREAD_STATE``.
_STATES = (
    "Initialized Ready Running Standby Terminated Waiting Transition DeferredReady"
    " GateWait WaitingForProcessInSwap"
).split()
#: ``KWAIT_REASON``; ``WrSuspended`` is written ``Suspended`` like ``Get-Process`` does.
_REASONS = (
    "Executive FreePage PageIn PoolAllocation DelayExecution Suspended UserRequest"
    " WrExecutive WrFreePage WrPageIn WrPoolAllocation WrDelayExecution Suspended"
    " WrUserRequest WrSpare0 WrQueue WrLpcReceive WrLpcReply WrVirtualMemory WrPageOut"
    " WrRendezvous WrKeyedEvent WrTerminated WrProcessInSwap WrCpuRateControl"
    " WrCalloutStack WrKernel WrResource WrPushLock WrMutex WrQuantumEnd WrDispatchInt"
    " WrPreempted WrYieldExecution WrFastMutex WrGuardedMutex WrRundown"
    " WrAlertByThreadId WrDeferredPreempt"
).split()


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_uint16),
        ("maximum_length", ctypes.c_uint16),
        ("buffer", ctypes.c_void_p),
    ]


class _ProcessInfo(ctypes.Structure):
    """``SYSTEM_PROCESS_INFORMATION``, followed by its threads."""

    _fields_ = [
        ("next_entry_offset", ctypes.c_uint32),
        ("number_of_threads", ctypes.c_uint32),
        ("working_set_private_size", ctypes.c_int64),
        ("hard_fault_count", ctypes.c_uint32),
        ("number_of_threads_high_watermark", ctypes.c_uint32),
        ("cycle_time", ctypes.c_uint64),
        ("create_time", ctypes.c_int64),
        ("user_time", ctypes.c_int64),
        ("kernel_time", ctypes.c_int64),
        ("image_name", _UnicodeString),
        ("base_priority", ctypes.c_long),
        ("unique_process_id", ctypes.c_void_p),
        ("inherited_from_unique_process_id", ctypes.c_void_p),
        ("handle_count", ctypes.c_uint32),
        ("session_id", ctypes.c_uint32),
        ("unique_process_key", ctypes.c_void_p),
        ("peak_virtual_size", ctypes.c_size_t),
        ("virtual_size", ctypes.c_size_t),
        ("page_fault_count", ctypes.c_uint32),
        ("peak_working_set_size", ctypes.c_size_t),
        ("working_set_size", ctypes.c_size_t),
        ("quota_peak_paged_pool_usage", ctypes.c_size_t),
        ("quota_paged_pool_usage", ctypes.c_size_t),
        ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
        ("quota_non_paged_pool_usage", ctypes.c_size_t),
        ("pagefile_usage", ctypes.c_size_t),
        ("peak_pagefile_usage", ctypes.c_size_t),
        ("private_page_count", ctypes.c_size_t),
        ("read_operation_count", ctypes.c_int64),
        ("write_operation_count", ctypes.c_int64),
        ("other_operation_count", ctypes.c_int64),
        ("read_transfer_count", ctypes.c_int64),
        ("write_transfer_count", ctypes.c_int64),
        ("other_transfer_count", ctypes.c_int64),
    ]


class _ThreadInfo(ctypes.Structure):
    """``SYSTEM_THREAD_INFORMATION``."""

    _fields_ = [
        ("kernel_time", ctypes.c_int64),
        ("user_time", ctypes.c_int64),
        ("create_time", ctypes.c_int64),
        ("wait_time", ctypes.c_uint32),
        ("start_address", ctypes.c_void_p),
        ("unique_process", ctypes.c_void_p),
        ("unique_thread", ctypes.c_void_p),
        ("priority", ctypes.c_long),
        ("base_priority", ctypes.c_long),
        ("context_switches", ctypes.c_uint32),
        ("thread_state", ctypes.c_uint32),
        ("wait_reason", ctypes.c_uint32),
    ]


@dataclass
class Thread:
    tid: int
    state: str
    reason: str
    cpu: float

    @property
    def group(self) -> str:
        """``Waiting/Suspended``, as ``Get-Process`` groups threads; the reason
        only for a waiting thread."""
        return f"{self.state}/{self.reason}" if self.state == "Waiting" else self.state


@dataclass
class Process:
    pid: int
    parent: int
    name: str
    born: float | None  # Unix time; None for the idle process and the system
    cpu: float
    working_set: int
    threads: list[Thread] = field(default_factory=list)


def processes() -> list[Process]:
    """Every process of this machine (Windows only), from the kernel."""
    if sys.platform != "win32":
        raise OSError("NtQuerySystemInformation is Windows only")
    query = ctypes.WinDLL("ntdll").NtQuerySystemInformation
    query.argtypes = [
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    query.restype = ctypes.c_ulong
    size = ctypes.c_ulong(1 << 20)
    for _ in range(_TRIES):
        buf = ctypes.create_string_buffer(size.value + _SLACK)
        status = query(_SYSTEM_PROCESS_INFORMATION, buf, len(buf), ctypes.byref(size))
        if status == 0:
            return parse(buf)
        if status != _TOO_SMALL:
            raise OSError(f"NtQuerySystemInformation: status 0x{status:08X}")
    raise OSError("NtQuerySystemInformation: the buffer kept growing")


def parse(buf: ctypes.Array) -> list[Process]:
    """The processes of a ``SystemProcessInformation`` buffer."""
    base, out, offset = ctypes.addressof(buf), [], 0
    while True:
        info = _ProcessInfo.from_address(base + offset)
        threads_at = base + offset + ctypes.sizeof(_ProcessInfo)
        out.append(_process(info, threads_at))
        if not info.next_entry_offset:
            return out
        offset += info.next_entry_offset


def _process(info: _ProcessInfo, threads_at: int) -> Process:
    name = info.image_name
    text = (
        ctypes.string_at(name.buffer, name.length).decode("utf-16-le", "replace")
        if name.buffer and name.length
        else ("Idle" if not info.unique_process_id else "?")
    )
    threads = []
    for i in range(info.number_of_threads):
        t = _ThreadInfo.from_address(threads_at + i * ctypes.sizeof(_ThreadInfo))
        threads.append(
            Thread(
                tid=t.unique_thread or 0,
                state=_name(_STATES, t.thread_state),
                reason=_name(_REASONS, t.wait_reason),
                cpu=(t.kernel_time + t.user_time) / 1e7,
            )
        )
    return Process(
        pid=info.unique_process_id or 0,
        parent=info.inherited_from_unique_process_id or 0,
        name=text,
        born=unix_time(info.create_time),
        cpu=(info.kernel_time + info.user_time) / 1e7,
        working_set=info.working_set_size,
        threads=threads,
    )


def tree(root: int, listed: list[Process] | None = None, max_lines: int = 300) -> str:
    """*root* and its descendants (the kernel's list, or *listed*), one row
    each with its threads grouped by state and wait reason, then the threads
    of *root* one by one."""
    listed = processes() if listed is None else listed
    by_pid = {p.pid: p for p in listed}
    if root not in by_pid:
        return f"no process {root}"
    children: dict[int, list[Process]] = {}
    for p in listed:
        # a pid reused by a process born before its parent is not its child
        parent = by_pid.get(p.parent)
        if parent is not None and p.pid != p.parent and _after(p, parent):
            children.setdefault(p.parent, []).append(p)
    out, stack, seen = [], [(by_pid[root], 0)], set()
    while stack:
        p, depth = stack.pop()
        if p.pid in seen:
            continue
        seen.add(p.pid)
        out.append(f"{'  ' * depth}{_row(p)}")
        stack.extend(
            (c, depth + 1) for c in sorted(children.get(p.pid, []), key=_born, reverse=True)
        )
    out.append(f"threads of {root} (id state wait cpu):")
    out.extend(
        f"  {t.tid} {t.state} {t.reason} {t.cpu:.1f}s" for t in by_pid[root].threads[:max_lines]
    )
    return "\n".join(out)


def born_since(start: float, listed: list[Process] | None = None) -> list[str]:
    """The processes born at *start* (Unix time) or later, oldest first."""
    listed = processes() if listed is None else listed
    young = sorted((p for p in listed if p.born is not None and p.born >= start), key=_born)
    return [f"  pid {p.pid} {p.name} parent={p.parent} born@{int(p.born * 1000)}" for p in young]


def _row(p: Process) -> str:
    counts: dict[str, int] = {}
    for t in p.threads:
        counts[t.group] = counts.get(t.group, 0) + 1
    groups = " ".join(f"{n}x{group}" for group, n in counts.items())
    born = f"born@{int(p.born * 1000)}" if p.born is not None else "born=?"
    return (
        f"pid {p.pid} {p.name} cpu={p.cpu:.1f}s ws={p.working_set >> 20}MB {born} threads: {groups}"
    )


def _born(p: Process) -> float:
    return p.born or 0.0


def _after(child: Process, parent: Process) -> bool:
    return child.born is None or parent.born is None or child.born >= parent.born


def unix_time(filetime: int) -> float | None:
    """A ``FILETIME`` (100 ns from 1601) as Unix time; ``None`` when unset."""
    return (filetime - _EPOCH_TICKS) / 1e7 if filetime > 0 else None


def _name(names: list[str], value: int) -> str:
    return names[value] if 0 <= value < len(names) else str(value)


__all__ = ["Process", "Thread", "born_since", "parse", "processes", "tree", "unix_time"]

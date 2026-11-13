"""Who holds the read-write lock that threads of a stuck macOS process wait
for, for the hang probe.

``sample`` shows a thread parked in ``__psynch_rw_wrlock`` (or ``rdlock``),
not the lock nor its owner. lldb, attached for a moment and detached, finds
each parked thread's lock (a callee-saved register of the waiting frames that
points at a ``pthread_rwlock_t`` signature), prints its words, and names the
thread whose id is stored in them (macOS records the writer that holds it), if
any, with that thread's stack. Nothing runs unless a thread waits on such a lock.
Blocking: call it in a thread.
"""

from __future__ import annotations

import os
import tempfile

from tests import process_snapshot

#: The first word of a ``pthread_rwlock_t``: ``'RWLK'`` once used, then the
#: static initialiser's (libpthread's ``_PTHREAD_RWLOCK_SIG`` and ``_SIG_init``).
RWLOCK_SIGS = (0x52574C4B, 0x2DA8B3B4)
#: A frame of ``sample`` that waits on a read-write lock.
PARKED = "__psynch_rw_"

#: Run by lldb's own Python (``command script import``), attached to the process.
LLDB_SCRIPT = f'''
import lldb

SIGS = ({", ".join(hex(sig) for sig in RWLOCK_SIGS)})
PARKED = "{PARKED}"
SAVED = ("x19", "x20", "x21", "x22", "x23", "x24", "x25", "x26", "x27", "x28",
         "rbx", "r12", "r13", "r14", "r15")
WORDS = 48


def _read(process, addr, size):
    err = lldb.SBError()
    value = process.ReadUnsignedFromMemory(addr, size, err)
    return None if err.Fail() else value


def _frame(f):
    name = f.GetFunctionName() or "?"
    module = f.GetModule().GetFileSpec().GetFilename() or "?"
    addr = f.GetPCAddress()
    offset = addr.GetFileAddress()
    return "%s (%s, file address 0x%x)" % (name, module, offset)


def _lock_of(process, frames):
    for f in frames[:8]:
        for name in SAVED:
            reg = f.FindRegister(name)
            if not reg.IsValid():
                continue
            addr = reg.GetValueAsUnsigned()
            first = _read(process, addr, 8) if addr else None
            if first is not None and first & 0xFFFFFFFF in SIGS:
                return addr
    return None


def __lldb_init_module(debugger, _dict):
    process = debugger.GetSelectedTarget().GetProcess()
    threads = {{t.GetThreadID(): t for t in process}}
    print("attached to %d, %d threads" % (process.GetProcessID(), len(threads)))
    locks = {{}}
    for thread in process:
        frames = [thread.GetFrameAtIndex(i) for i in range(thread.GetNumFrames())]
        names = [f.GetFunctionName() or "" for f in frames]
        wait = next((n for n in names if n.startswith(PARKED)), None)
        if wait is None:
            continue
        lock = _lock_of(process, frames)
        caller = next((f for f in frames if "libsystem" not in
                       (f.GetModule().GetFileSpec().GetFilename() or "")), None)
        print("thread %d %s waits (%s) on rwlock %s, from %s" % (
            thread.GetThreadID(), thread.GetName() or "", wait[len(PARKED):],
            hex(lock) if lock else "? (not in a saved register)",
            _frame(caller) if caller else "?"))
        if lock:
            locks.setdefault(lock, []).append(thread.GetThreadID())
    for lock, waiters in locks.items():
        words = [_read(process, lock + 4 * i, 4) for i in range(WORDS)]
        print("rwlock %s, %d waiter(s); its 32-bit words:" % (hex(lock), len(waiters)))
        for row in range(0, WORDS, 8):
            print("  +%03x: %s" % (4 * row, " ".join(
                "????????" if w is None else "%08x" % w for w in words[row:row + 8])))
        # The sequence words L, S, U sit at the first 16-byte boundary past +32;
        # counts step by 0x100, the low byte of L is its state (libpthread).
        seq = (lock + 32 + 0xF) & ~0xF
        lcntval, rwseq, ucntval = (_read(process, seq + 4 * i, 4) for i in range(3))
        if None not in (lcntval, rwseq, ucntval):
            bits = [b for b, m in (("K", 1), ("E", 2), ("W", 4), ("U", 0x40), ("I", 0x80))
                    if lcntval & m]
            print("  lcntval %08x (%s) rw_seq %08x ucntval %08x: %d grant(s) or wait(s)"
                  " not unlocked" % (lcntval, "".join(bits) or "-", rwseq, ucntval,
                  ((lcntval & ~0xFF) - (ucntval & ~0xFF)) % (1 << 32) >> 8))
        owners = set()
        for i in range(WORDS - 1):
            value = _read(process, lock + 4 * i, 8)
            if value in threads and value not in waiters:
                owners.add((4 * i, value))
        if not owners:
            print("  held for writing by: nobody (no thread id of the process in its words)")
        for offset, tid in sorted(owners):
            owner = threads[tid]
            print("  held for writing by: thread %d %s (its id at +%03x); its stack:" % (
                tid, owner.GetName() or "", offset))
            for i in range(min(owner.GetNumFrames(), 40)):
                print("    " + _frame(owner.GetFrameAtIndex(i)))
'''


def _run(cmd: list[str]) -> tuple[str, bool]:
    return process_snapshot._run(cmd, process_snapshot.COMMAND_TIMEOUT)


def _sudo() -> list[str]:
    return process_snapshot._sudo()


def rwlocks(pid: int, sample: str) -> str:
    """The read-write locks that *sample*'s parked threads of *pid* wait
    for, and who holds them; ``""`` when no thread waits on one."""
    if PARKED not in sample:
        return ""
    with tempfile.TemporaryDirectory(prefix="tellurium_locks_") as tmp:
        path = os.path.join(tmp, "lock_owner.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(LLDB_SCRIPT)
        os.chmod(tmp, 0o755)
        cmd = [*_sudo(), "lldb", "-p", str(pid), "--batch"]
        cmd += ["-o", f"command script import {path}", "-o", "process detach"]
        said, _ = _run(cmd)
    return "read-write locks waited on (lldb):\n" + "\n".join(
        "  " + line for line in said.strip().splitlines()
    )

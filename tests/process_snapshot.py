"""What a process and its children are doing right now, for the hang probe.

One row per process of the tree (``pid <n> <name> state=<s> ...``) with its
birth (``born=``: seconds from the stalled send, else the UTC clock), then what
each system can say about where the root process is stuck:

* Linux: ``/proc`` (state, wait channel and kernel stack of each thread of
  the root);
* macOS: ``sample`` (the user-space call graph of every thread of the root);
  who holds a read-write lock its threads wait on is the hang probe's to ask
  (``tests.blocked_locks``), once the sample is in its report;
* Windows: the threads of each process grouped by state and wait reason
  (``Suspended`` for a suspended one), and those of the root one by one, read
  at once from the kernel in this process (``tests.windows_processes``: a
  frozen runner did not even start PowerShell); then the same through
  PowerShell, with each process's kind (``--type``).

:func:`machine` adds the whole machine: on Windows the processes born since
the send (from the kernel), the events of shadow copies (VSS, volsnap) of the
last minutes (``tests.shadow_copy_events``), the busiest over a second and the
CPU and disk counters (PowerShell); elsewhere
the load average (and Linux's pressure stall information).

Nothing runs as root unless ``$TELLURIUM_HANG_SUDO`` is ``1`` (the CI sets
it: the kernel stack on Linux, ``sample`` of the hardened Chrome on macOS,
through ``sudo -n``). A command past its deadline is ended with every process
it started. Blocking (files, subprocesses with their own deadlines): call it
in a thread.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests import shadow_copy_events, windows_processes

#: How long ``sample`` watches the root process (macOS).
SAMPLE_SECONDS = 3
#: Deadline of each subprocess: a stalled runner froze even ``Get-Process`` for 20 s.
COMMAND_TIMEOUT = 45.0
#: Deadline of the Windows snapshot and machine view through PowerShell: a
#: stalled runner did not finish it in 45 s (run 43391051756).
WINDOWS_FULL_TIMEOUT = 20.0
#: Past a command's deadline: how long ``taskkill /T`` gets to end its tree
#: (Windows), then how long its pipes get to close.
TASKKILL_TIMEOUT = 10.0
PIPES_TIMEOUT = 5.0
#: How far back the view of the machine looks for shadow copy events (Windows).
EVENTS_WINDOW = 600.0
#: ``1``: the commands that need root run through ``sudo -n`` (the CI only).
SUDO_ENV = "TELLURIUM_HANG_SUDO"
#: Threads of the root process listed (Linux, Windows).
MAX_LINES = 300
#: Lines of ``sample``'s output kept (macOS): all of a browser process's ~60 threads.
MAX_SAMPLE_LINES = 5000
_TYPE = re.compile(r"--type=(\S+)")
#: A birth (or a moment, ``at@``) as the systems' parts write it: Unix time in ms.
_BORN = re.compile(r"\b(born|at)@(\d+)")


def snapshot(pid: int, since: float | None = None) -> str:
    """The tree rooted at *pid* and where its root is; each birth in seconds
    from *since* (Unix time), else on the UTC clock. Never raises."""
    try:
        if sys.platform == "win32":
            text = _windows(pid)
        elif sys.platform == "darwin":
            text = _macos(pid)
        else:
            text = _linux(pid)
    except Exception as exc:
        return f"(no snapshot of {pid}: {exc!r})"
    return births(text, since)


def machine(since: float | None = None) -> str:
    """The whole machine around the stall (births in seconds from *since*);
    never raises."""
    try:
        if sys.platform == "win32":
            text = _windows_machine(since)
        else:
            text = _posix_machine()
    except Exception as exc:
        return f"(no view of the machine: {exc!r})"
    return births(text.strip(), since)


def births(text: str, since: float | None) -> str:
    """Each ``born@<ms>`` (and ``at@<ms>``) of *text* in seconds from *since*,
    else on the UTC clock."""

    def say(match: re.Match) -> str:
        word, at = match.group(1), int(match.group(2)) / 1000
        if since is not None:
            return f"{word}={at - since:+.2f}s"
        clock = time.strftime("%H:%M:%S", time.gmtime(at))
        return f"{word}={clock}.{int(at * 1000) % 1000:03d}Z"

    return _BORN.sub(say, text)


def _born_tag(at: float) -> str:
    return f"born@{int(at * 1000)}"


def _run(cmd: list[str], timeout: float = COMMAND_TIMEOUT) -> tuple[str, bool]:
    """What *cmd* printed, and whether it ended well within *timeout*; past
    it, *cmd* is ended with every process it started."""
    group = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if sys.platform == "win32"
        else {"start_new_session": True}
    )
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **group
        )
    except OSError as exc:
        return f"({cmd[0]} failed: {exc!r})", False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _end_tree(proc)
        try:
            out, _ = proc.communicate(timeout=PIPES_TIMEOUT)
        except subprocess.TimeoutExpired:  # a process outside the group holds the pipes
            out = ""
        return f"({cmd[0]} timed out after {timeout:g}s)\n{out or ''}".strip(), False
    said = (out or "") + (f"\n(stderr) {err.strip()}" if err and err.strip() else "")
    return said, proc.returncode == 0


def _end_tree(proc: subprocess.Popen) -> None:
    """End *proc* and what it started: ``taskkill /T`` on Windows; on POSIX
    its process group, ``SIGTERM`` first (``sudo`` passes it on to a command
    it runs as root), then ``SIGKILL``."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=TASKKILL_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        _kill(proc)
        return
    for sig, grace in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(grace)
            if sig == signal.SIGTERM:
                time.sleep(0.2)  # what it started may still be ending
        except subprocess.TimeoutExpired:
            continue
    _kill(proc)


def _kill(proc: subprocess.Popen) -> None:
    """The last word on *proc*; a ``sudo`` running as root may refuse it, and
    the snapshot goes on without it."""
    try:
        proc.kill()
    except OSError:
        pass


def _sudo() -> list[str]:
    """``sudo -n`` when the CI asks for it and it needs no password, else nothing:
    never root on a developer's machine."""
    if os.environ.get(SUDO_ENV) != "1" or shutil.which("sudo") is None:
        return []
    try:
        ok = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=10).returncode
    except (OSError, subprocess.SubprocessError):
        return []
    return ["sudo", "-n"] if ok == 0 else []


# --- Linux ------------------------------------------------------------------


def _linux(pid: int) -> str:
    if not Path(f"/proc/{pid}").exists():
        return f"no process {pid}"
    out = [_linux_row(p, depth) for p, depth in _linux_tree(pid)]
    out.append(f"threads of {pid} (tid name state wchan):")
    tids = sorted(int(t.name) for t in Path(f"/proc/{pid}/task").iterdir())
    for tid in tids[:MAX_LINES]:
        base = f"/proc/{pid}/task/{tid}"
        name, state, _ = _stat(f"{base}/stat")
        out.append(f"  {tid} {name} {state} {_read(f'{base}/wchan') or '-'}")
    out.append(f"kernel stack of {pid}:")
    out.append(_kernel_stack(pid))
    return "\n".join(out)


def _linux_tree(root: int) -> list[tuple[int, int]]:
    children: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                _, _, ppid = _stat(f"{entry}/stat")
            except OSError:
                continue
            children.setdefault(ppid, []).append(int(entry.name))
    tree, stack = [], [(root, 0)]
    while stack:
        pid, depth = stack.pop()
        tree.append((pid, depth))
        stack.extend((c, depth + 1) for c in sorted(children.get(pid, []), reverse=True))
    return tree


def _linux_row(pid: int, depth: int) -> str:
    fields = {}
    for line in _read(f"/proc/{pid}/status").splitlines():
        key, _, value = line.partition(":")
        fields[key] = " ".join(value.split())
    kind = _TYPE.search(_read(f"/proc/{pid}/cmdline").replace("\0", " "))
    return (
        f"{'  ' * depth}pid {pid} {fields.get('Name', '?')}"
        f"{' ' + kind.group(1) if kind else ''} state={fields.get('State', '?')}"
        f" threads={fields.get('Threads', '?')} rss={fields.get('VmRSS', '?')}"
        f" wchan={_read(f'/proc/{pid}/wchan') or '-'}"
        f" switches={fields.get('voluntary_ctxt_switches', '?')}"
        f"/{fields.get('nonvoluntary_ctxt_switches', '?')} {_linux_born(pid)}"
    )


def _linux_born(pid: int) -> str:
    """``born@`` from the start of *pid* in clock ticks after boot."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        start = int(text[text.rindex(")") + 2 :].split()[19]) / os.sysconf("SC_CLK_TCK")
        uptime = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return "born=?"
    return _born_tag(time.time() - (uptime - start))


def _posix_machine() -> str:
    out = [f"load average {' '.join(f'{x:.2f}' for x in os.getloadavg())} (cpus {os.cpu_count()})"]
    for kind in ("cpu", "io", "memory"):
        some = _read(f"/proc/pressure/{kind}").splitlines()
        if some:
            out.append(f"pressure {kind}: {some[0]}")
    return "\n".join(out)


def _stat(path: str) -> tuple[str, str, int]:
    """(name, state, parent pid) from a ``stat`` file: the name may hold spaces."""
    text = Path(path).read_text()
    name = text[text.index("(") + 1 : text.rindex(")")]
    state, ppid = text[text.rindex(")") + 2 :].split()[:2]
    return name, state, int(ppid)


def _read(path: str) -> str:
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return ""


def _kernel_stack(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/stack").read_text().strip() or "(empty)"
    except OSError as exc:
        sudo = _sudo()
        if not sudo:
            return f"(not readable: {exc.strerror})"
        return _run([*sudo, "cat", f"/proc/{pid}/stack"])[0].strip() or "(empty)"


# --- macOS ------------------------------------------------------------------


def _macos(pid: int) -> str:
    rows, _ = _run(["ps", "-A", "-o", "pid=,ppid=,state=,pcpu=,rss=,etime=,command="])
    procs: dict[int, tuple[int, str]] = {}
    for line in rows.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            procs[int(parts[0])] = (int(parts[1]), line)
    if pid not in procs:
        return f"no process {pid}"
    out = []
    stack = [(pid, 0)]
    while stack:
        p, depth = stack.pop()
        _, line = procs[p]
        out.append(f"{'  ' * depth}{_macos_row(line)}")
        kids = sorted((c for c, (pp, _) in procs.items() if pp == p), reverse=True)
        stack.extend((c, depth + 1) for c in kids)
    out.append(f"sample of {pid}, {SAMPLE_SECONDS} s:")
    out.append(_sample(pid))
    return "\n".join(out)


def _macos_row(line: str) -> str:
    pid, _ppid, state, cpu, rss, etime, command = line.split(None, 6)
    kind = _TYPE.search(command)
    name = Path(command.split(" --", 1)[0]).name
    return (
        f"pid {pid} {name}{' ' + kind.group(1) if kind else ''} state={state}"
        f" cpu={cpu}% rss={rss}K elapsed={etime} {_born_tag(time.time() - _seconds(etime))}"
    )


def _seconds(etime: str) -> int:
    """``[[dd-]hh:]mm:ss`` of ``ps`` in seconds."""
    days, _, clock = etime.rpartition("-")
    total = 0
    for part in clock.split(":"):
        total = total * 60 + int(part)
    return total + int(days or 0) * 86400


def _sample(pid: int) -> str:
    with tempfile.TemporaryDirectory(prefix="tellurium_sample_") as tmp:
        path = os.path.join(tmp, "sample.txt")
        cmd = ["sample", str(pid), str(SAMPLE_SECONDS), "-mayDie", "-file", path]
        said, _ = _run([*_sudo(), *cmd])
        try:
            text = Path(path).read_text(errors="replace")
        except OSError:
            return f"(no sample: {said.strip()[:500]})"
    return trimmed_sample(text)


def trimmed_sample(text: str) -> str:
    """The call graph of every thread, the stacks it ends on most, and where
    Chrome's binaries are loaded (to symbolize its ``ChromeMain + n`` frames)."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("Call graph:")), 0)
    images = next((i for i, line in enumerate(lines) if line.startswith("Binary Images:")), None)
    kept = [line[:240] for line in lines[start:images] if line.strip()][:MAX_SAMPLE_LINES]
    if images is not None:
        kept.append(lines[images])
        kept.extend(line.strip() for line in lines[images + 1 :] if "Chrome" in line)
    return "\n".join(kept)


# --- Windows ----------------------------------------------------------------

_POWERSHELL = r"""
$root = {pid}
$all = @(Get-CimInstance Win32_Process |
  Select-Object ProcessId,ParentProcessId,Name,CommandLine,CreationDate)
if (-not ($all | Where-Object {{ $_.ProcessId -eq $root }})) {{ "no process $root"; exit }}
$queue = New-Object System.Collections.Generic.List[object]
$queue.Add(@($root, 0))
$i = 0
while ($i -lt $queue.Count) {{
  $id, $depth = $queue[$i]; $i++
  $info = $all | Where-Object {{ $_.ProcessId -eq $id }} | Select-Object -First 1
  $kind = if ($info.CommandLine -match '--type=(\S+)') {{ ' ' + $Matches[1] }} else {{ '' }}
  $p = Get-Process -Id $id -ErrorAction SilentlyContinue
  if ($p) {{
    $groups = ($p.Threads | Group-Object ThreadState,WaitReason |
      ForEach-Object {{ '{{0}}x{{1}}' -f $_.Count, ($_.Name -replace ', ', '/') }}) -join ' '
    $born = ([DateTimeOffset]$info.CreationDate).ToUnixTimeMilliseconds()
    '{{0}}pid {{1}} {{2}}{{3}} cpu={{4:N1}}s ws={{5}}MB born@{{6}} threads: {{7}}' -f ('  ' * $depth),
      $id, $info.Name, $kind, $p.CPU, [int]($p.WorkingSet64 / 1MB), $born, $groups
  }}
  foreach ($c in ($all | Where-Object {{ $_.ParentProcessId -eq $id }})) {{
    $queue.Add(@($c.ProcessId, ($depth + 1)))
  }}
}}
"threads of $root (id state wait cpu):"
(Get-Process -Id $root).Threads | Select-Object -First {max_lines} |
  ForEach-Object {{ '  {{0}} {{1}} {{2}} {{3}}' -f $_.Id, $_.ThreadState, $_.WaitReason,
    $_.TotalProcessorTime }}
"""


def _windows(pid: int) -> str:
    """The tree from the kernel at once, then through PowerShell (kinds too)."""
    try:
        kernel = windows_processes.tree(pid, max_lines=MAX_LINES)
    except Exception as exc:  # noqa: BLE001 — PowerShell may still say it
        kernel = f"(no list from the kernel: {exc!r})"
    if kernel.startswith("no process"):
        return kernel
    script = _POWERSHELL.format(pid=int(pid), max_lines=MAX_LINES)
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    full, _ = _run(cmd, timeout=WINDOWS_FULL_TIMEOUT)
    return (
        f"from the kernel, at once:\n{kernel}\nthrough PowerShell, with the kinds:\n{full.strip()}"
    )


def _windows_machine(since: float | None) -> str:
    """Births from the kernel and shadow copy events (``wevtutil``) first,
    then PowerShell's view; a log of events that timed out is asked again
    last."""
    now = time.time() if since is None else since
    start = (now - 60.0) if since is None else since - 5.0
    when = "a minute ago" if since is None else "5 s before the send"
    try:
        born = windows_processes.born_since(start) or ["  (none)"]
    except Exception as exc:  # noqa: BLE001 — the rest of the view goes on
        born = [f"  (no list from the kernel: {exc!r})"]
    out = [f"processes born on the machine since {when} (from the kernel):", *born]
    events = shadow_copy_events.Events(window=EVENTS_WINDOW + max(0.0, time.time() - now))
    out.append(
        f"shadow copy events since 10 minutes before {'now' if since is None else 'the send'}"
        " (Application and System logs, wevtutil):"
    )
    out.append(events.read())
    view, _ = _run(_windows_machine_cmd(), timeout=WINDOWS_FULL_TIMEOUT)
    out.append(view.strip())
    out.append(events.read_missed())
    return "\n".join(line for line in out if line)


#: The busiest processes over a second, and the CPU, disk and memory counters.
_MACHINE = r"""
$services = @{}
Get-CimInstance Win32_Service -Filter "State='Running'" | ForEach-Object {
  $services[[int]$_.ProcessId] += @($_.Name) }
"busiest processes over 1 s (CPU seconds used):"
$before = @{}
Get-Process | ForEach-Object { $before[$_.Id] = $_.CPU }
Start-Sleep -Milliseconds 1000
Get-Process | ForEach-Object { [pscustomobject]@{ Id = $_.Id; Name = $_.Name;
  Used = ($_.CPU - $before[$_.Id]) } } | Sort-Object Used -Descending | Select-Object -First 8 |
  ForEach-Object { '  pid {0} {1} cpu={2:N2}s {3}' -f $_.Id, $_.Name, $_.Used,
    ($services[[int]$_.Id] -join ',') }
"busiest processes on the disk (bytes/s, all I/O):"
$io = (Get-Counter '\Process(*)\IO Data Bytes/sec', '\Process(*)\ID Process' `
  -ErrorAction SilentlyContinue).CounterSamples
$ids = @{}
$io | Where-Object { $_.Path -like '*\id process' } |
  ForEach-Object { $ids[$_.InstanceName] = [int]$_.CookedValue }
$io | Where-Object { $_.Path -like '*\io data bytes/sec' -and $_.InstanceName -ne '_total' } |
  Sort-Object CookedValue -Descending | Select-Object -First 6 | ForEach-Object {
    $id = $ids[$_.InstanceName]
    '  pid {0} {1} io={2:N0}B/s {3}' -f $id, $_.InstanceName, $_.CookedValue,
      ($services[$id] -join ',') }
"counters:"
$names = '\Processor(_Total)\% Processor Time', '\PhysicalDisk(_Total)\Current Disk Queue Length',
  '\PhysicalDisk(_Total)\% Disk Time', '\Memory\Available MBytes'
(Get-Counter $names -ErrorAction SilentlyContinue).CounterSamples |
  ForEach-Object { '  {0} {1:N1}' -f $_.Path, $_.CookedValue }
"""


def _windows_machine_cmd() -> list[str]:
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", _MACHINE]

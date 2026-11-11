"""What a process and its children are doing right now, for the hang probe.

One row per process of the tree (``pid <n> <name> state=<s> ...``), then what
each system can say about where the root process is stuck:

* Linux: ``/proc`` (state, wait channel and kernel stack of each thread of
  the root, the kernel stack through ``sudo -n`` when not readable);
* macOS: ``sample`` (the user-space call graph of every thread of the root,
  through ``sudo -n`` when it can: Chrome is a hardened binary);
* Windows: the threads of each process grouped by state and wait reason
  (``Suspended`` for a suspended one), and those of the root one by one.

Blocking (files, subprocesses with their own deadlines): call it in a thread.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: How long ``sample`` watches the root process (macOS).
SAMPLE_SECONDS = 3
#: Deadline of each subprocess: a stalled runner froze even ``Get-Process`` for 20 s.
COMMAND_TIMEOUT = 45.0
#: Threads of the root process listed (Linux, Windows).
MAX_LINES = 300
#: Lines of ``sample``'s output kept (macOS): all of a browser process's ~60 threads.
MAX_SAMPLE_LINES = 5000
_TYPE = re.compile(r"--type=(\S+)")


def snapshot(pid: int) -> str:
    """The tree rooted at *pid* and where its root is; never raises."""
    try:
        if sys.platform == "win32":
            return _windows(pid)
        if sys.platform == "darwin":
            return _macos(pid)
        return _linux(pid)
    except Exception as exc:
        return f"(no snapshot of {pid}: {exc!r})"


def _run(cmd: list[str]) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"({cmd[0]} failed: {exc!r})"
    return done.stdout + (f"\n(stderr) {done.stderr.strip()}" if done.stderr.strip() else "")


def _sudo() -> list[str]:
    """``sudo -n`` when it needs no password (the CI runners), else nothing."""
    if shutil.which("sudo") is None:
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
        f"/{fields.get('nonvoluntary_ctxt_switches', '?')}"
    )


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
        return _run([*sudo, "cat", f"/proc/{pid}/stack"]).strip() or "(empty)"


# --- macOS ------------------------------------------------------------------


def _macos(pid: int) -> str:
    rows = _run(["ps", "-A", "-o", "pid=,ppid=,state=,pcpu=,rss=,etime=,command="])
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
        f" cpu={cpu}% rss={rss}K elapsed={etime}"
    )


def _sample(pid: int) -> str:
    with tempfile.TemporaryDirectory(prefix="tellurium_sample_") as tmp:
        path = os.path.join(tmp, "sample.txt")
        cmd = ["sample", str(pid), str(SAMPLE_SECONDS), "-mayDie", "-file", path]
        said = _run([*_sudo(), *cmd])
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
$all = @(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine)
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
    '{{0}}pid {{1}} {{2}}{{3}} cpu={{4:N1}}s ws={{5}}MB threads: {{6}}' -f ('  ' * $depth), $id,
      $info.Name, $kind, $p.CPU, [int]($p.WorkingSet64 / 1MB), $groups
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
    script = _POWERSHELL.format(pid=int(pid), max_lines=MAX_LINES)
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script]).strip()

"""What Chrome and the machine were doing when a CDP command got no reply (R3-B, temporary).

Patched in for the whole run by ``hang_probe`` (an autouse session fixture): every
message Chrome sends is noted per router; when ``Session.send`` times out, the
traffic before it, a few probes and a process listing are printed (pytest shows
them under the failing test), then the timeout goes on as it was.
"""

from __future__ import annotations

import asyncio
import collections
import subprocess
import sys
import time
import weakref

import pytest

from tellurium.browser.process import BrowserProcess
from tellurium.cdp.transport._session import Session, SessionRouter

_traffic: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_procs: weakref.WeakSet = weakref.WeakSet()
_T0 = time.monotonic()
_REAL_SEND = Session.send  # the probes' own sends are not probed
_MIN_LIMIT = 8.0
_WATCH = 3.0  # seconds a command may wait before the report: Chrome answers in ms
_SNAPSHOT_EVERY = 30.0  # the process listing costs a PowerShell: not on every report
_last_snapshot = [-_SNAPSHOT_EVERY]
_reports: set = set()
_events: collections.deque = collections.deque(maxlen=60)


_config: list = []  # pytest's config, to write past the output capture


def _emit(text: str) -> None:
    """To the terminal at once, even under a passing test (whose output pytest drops)."""
    if _config:
        capman = _config[0].pluginmanager.getplugin("capturemanager")
        reporter = _config[0].pluginmanager.getplugin("terminalreporter")
        if capman is not None and reporter is not None:
            with capman.global_and_fixture_disabled():
                reporter.write_line("")
                reporter.write_line(text)
            return
    print(text, flush=True)


def note(what: str) -> None:
    """Something a test fixture saw (a proxy's connection, a request), for the report."""
    _events.append((time.monotonic(), what))


def _note(router, msg: dict) -> None:
    q = _traffic.setdefault(router, collections.deque(maxlen=300))
    what = msg.get("method") or f"reply {msg.get('id')}" + (" ERR" if "error" in msg else "")
    q.append((time.monotonic(), what, (msg.get("sessionId") or "")[:6]))


def _snapshot() -> str:
    if sys.platform == "win32":
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process | Sort-Object CPU -Descending | Select-Object -First 25 "
            "Id,ProcessName,CPU,WS,StartTime,Responding | Format-Table -AutoSize | Out-String -Width 200;"
            "(Get-Counter '\\Process(*)\\% Processor Time' -ErrorAction SilentlyContinue).CounterSamples"
            " | Sort-Object CookedValue -Descending | Select-Object -First 15 InstanceName,CookedValue"
            " | Format-Table -AutoSize | Out-String -Width 200;"
            "'chrome: ' + (Get-Process chrome -ErrorAction SilentlyContinue).Count;"
            "Get-CimInstance Win32_Processor | Select LoadPercentage | Out-String",
        ]
    else:
        cmd = [
            "sh",
            "-c",
            "uptime; ps -A -o pid,ppid,pcpu,pmem,etime,state,comm -r | head -30;"
            " echo chrome: $(ps -A -o comm | grep -ci chrome)",
        ]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except Exception as e:  # noqa: BLE001
        return f"(no snapshot: {e!r})"


def _stuck(pid: int) -> str:
    """Where Chrome's browser process is: its threads' states, its main thread's stack."""
    if sys.platform == "win32":
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-Process -Id {pid}).Threads | Group-Object ThreadState,WaitReason"
            " | Select-Object Count,Name | Format-Table -AutoSize | Out-String -Width 200",
        ]
    elif sys.platform == "darwin":
        cmd = [
            "sh",
            "-c",
            "ps -A -o pid,ppid,state,pcpu,etime,comm | grep -i chrom | cut -c1-140;"
            f" sample {pid} 2 -mayDie 2>&1 | sed -n '/^Call graph:/,/^$/p' | head -90 | cut -c1-200;"
            " echo '--- fs_usage 3s (Chrome, Spotlight) ---';"
            " sudo -n fs_usage -w -t 3 -f filesys 2>/dev/null"
            " | grep -iE 'chrom|mdworker|mds|tellurium' | head -60 | cut -c1-220",
        ]
    else:
        cmd = ["ps", "-L", "-o", "tid,state,pcpu,wchan:32,comm", "-p", str(pid)]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except Exception as e:  # noqa: BLE001
        return f"(no stack: {e!r})"


def _machine() -> str:
    """Once per session: what the machine is doing besides the tests."""
    if sys.platform == "win32":
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-MpComputerStatus | Select-Object AMRunningMode,RealTimeProtectionEnabled,"
            "OnAccessProtectionEnabled,IoavProtectionEnabled,BehaviorMonitorEnabled | Format-List"
            " | Out-String; (Get-MpPreference).ExclusionPath -join ';'",
        ]
    elif sys.platform == "darwin":
        cmd = ["sh", "-c", "uptime; mdutil -as 2>&1 | head -20; echo TMPDIR=$TMPDIR"]
    else:
        cmd = ["uptime"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    except Exception as e:  # noqa: BLE001
        out = f"(no machine info: {e!r})"
    return "=== HANG PROBE machine\n" + out


async def _probe(label: str, coro, out: list[str]) -> bool:
    t = time.monotonic()
    try:
        res = await coro
        out.append(f"  probe {label}: ok in {time.monotonic() - t:.2f}s {str(res)[:200]}")
        return True
    except BaseException as e:  # noqa: BLE001
        out.append(f"  probe {label}: {type(e).__name__} {e} after {time.monotonic() - t:.2f}s")
        return False


async def _report(session: Session, method: str, sent_at: float, limit: float) -> None:
    router = session._router
    now = time.monotonic()
    out = [
        f"=== HANG PROBE: {method} (session {(session._session_id or 'root')[:6]}) "
        f"pending for {now - sent_at:.1f}s (limit {limit:g}s); run clock {now - _T0:.1f}s",
    ]
    reader = getattr(router, "_probe_task", None)
    out.append(f"  dispatch loop done: {reader.done() if reader else '?'}")
    q = list(_traffic.get(router, ()))
    during = [e for e in q if e[0] >= sent_at]
    out.append(f"  messages from Chrome since the send: {len(during)}")
    for t, what, sid in q[-25:]:
        out.append(f"    {t - sent_at:+8.2f}s {what} {sid}")
    seen = [e for e in _events if e[0] >= sent_at - 5]
    if seen:
        out.append("  fixture events around the send:")
        out.extend(f"    {t - sent_at:+8.2f}s {what}" for t, what in seen)
    root = router.root
    alive = await _probe(
        "root Browser.getVersion", _REAL_SEND(root, "Browser.getVersion", {}, 5), out
    )
    if session._session_id:
        ev = {
            "expression": "[document.visibilityState, location.href, document.readyState]",
            "returnByValue": True,
        }
        await _probe(
            "session Runtime.evaluate", _REAL_SEND(session, "Runtime.evaluate", ev, 5), out
        )
    for proc in [p for p in _procs if not alive and p.transport is router._transport]:
        pid = getattr(proc.process, "pid", None)
        if pid is not None:
            out.append(f"  --- chrome {pid} (this router) threads ---")
            out.append(await asyncio.to_thread(_stuck, pid))
    for proc in [p for p in _procs if p.process is not None and p.process.poll() is None]:
        tail = proc._output.text()[-3000:] if proc._output is not None else "(log file)"
        pid = getattr(proc.process, "pid", "?")
        out.append(f"  --- chrome {pid} output tail ---\n{tail}")
    if time.monotonic() - _last_snapshot[0] >= _SNAPSHOT_EVERY:
        _last_snapshot[0] = time.monotonic()
        out.append("  --- processes ---\n" + await asyncio.to_thread(_snapshot))
    _emit("\n".join(out))


async def _safe_report(session: Session, method: str, sent_at: float, limit: float) -> None:
    try:
        await _report(session, method, sent_at, limit)
    except Exception as e:  # noqa: BLE001
        _emit(f"=== HANG PROBE failed: {e!r}")


@pytest.fixture(scope="session", autouse=True)
def hang_probe(pytestconfig):
    _config.append(pytestconfig)
    _emit(_machine())
    real_send, real_handle, real_spawn = Session.send, Session._handle_message, BrowserProcess.spawn
    real_run, real_start = SessionRouter.run, BrowserProcess._start

    async def send(self, method, params=None, timeout=None):
        sent_at = time.monotonic()
        limit = self._router.default_timeout if timeout is None else timeout
        # Short limits are the tests' own frozen pages: probing them only delays those
        # tests past their bounds. The hangs looked for wait 10 s or 30 s; the report is
        # made while the command is still pending, whoever gives up on it later.
        watch, fired, outcome = None, [], "answered"
        if limit >= _MIN_LIMIT:
            loop = asyncio.get_running_loop()

            def fire():
                fired.append(True)
                task = loop.create_task(_safe_report(self, method, sent_at, limit))
                _reports.add(task)
                task.add_done_callback(_reports.discard)

            watch = loop.call_later(_WATCH, fire)
        try:
            return await real_send(self, method, params, timeout)
        except BaseException as e:
            outcome = type(e).__name__
            raise
        finally:
            if watch is not None:
                watch.cancel()
            if fired:
                took = time.monotonic() - sent_at
                _emit(f"=== HANG PROBE end: {method} {outcome} after {took:.1f}s")

    async def handle(self, msg):
        _note(self._router, msg)
        return await real_handle(self, msg)

    async def spawn(self, *a, **kw):
        _procs.add(self)
        return await real_spawn(self, *a, **kw)

    async def start(self, chrome_path, flags, env):
        if sys.platform == "win32" and not any(f.startswith("--enable-logging") for f in flags):
            flags = [*flags, "--enable-logging=stderr"]  # else a release build says nothing
        return await real_start(self, chrome_path, flags, env)

    async def run(self):
        self._probe_task = asyncio.current_task()
        return await real_run(self)

    Session.send, Session._handle_message, BrowserProcess.spawn = send, handle, spawn
    SessionRouter.run, BrowserProcess._start = run, start
    yield
    Session.send, Session._handle_message, BrowserProcess.spawn = real_send, real_handle, real_spawn
    SessionRouter.run, BrowserProcess._start = real_run, real_start


__all__ = ["hang_probe"]

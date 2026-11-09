"""What Chrome and the machine were doing when a CDP command got no reply (R3-B, temporary).

Patched in for the whole run by ``hang_probe`` (an autouse session fixture): every
message Chrome sends is noted per router; when ``Session.send`` times out, the
traffic before it, a few probes and a process listing are printed (pytest shows
them under the failing test), then the timeout goes on as it was.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
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


async def _probe(label: str, coro, out: list[str]) -> None:
    t = time.monotonic()
    try:
        res = await coro
        out.append(f"  probe {label}: ok in {time.monotonic() - t:.2f}s {str(res)[:200]}")
    except BaseException as e:  # noqa: BLE001
        out.append(f"  probe {label}: {type(e).__name__} {e} after {time.monotonic() - t:.2f}s")


async def _report(session: Session, method: str, sent_at: float, limit: float) -> None:
    router = session._router
    now = time.monotonic()
    out = [
        f"=== HANG PROBE: {method} (session {(session._session_id or 'root')[:6]}) "
        f"no reply in {limit:g}s; run clock {now - _T0:.1f}s",
    ]
    reader = getattr(router, "_probe_task", None)
    out.append(f"  dispatch loop done: {reader.done() if reader else '?'}")
    q = list(_traffic.get(router, ()))
    during = [e for e in q if e[0] >= sent_at]
    out.append(f"  messages from Chrome since the send: {len(during)}")
    for t, what, sid in q[-25:]:
        out.append(f"    {t - sent_at:+8.2f}s {what} {sid}")
    root = router.root
    await _probe("root Browser.getVersion", _REAL_SEND(root, "Browser.getVersion", {}, 5), out)
    if session._session_id:
        ev = {
            "expression": "[document.visibilityState, location.href, document.readyState]",
            "returnByValue": True,
        }
        await _probe(
            "session Runtime.evaluate", _REAL_SEND(session, "Runtime.evaluate", ev, 5), out
        )
    for proc in list(_procs):
        tail = proc._output.text()[-3000:] if proc._output is not None else "(log file)"
        pid = getattr(proc.process, "pid", "?")
        out.append(f"  --- chrome {pid} output tail ---\n{tail}")
    out.append("  --- processes ---\n" + await asyncio.to_thread(_snapshot))
    print("\n".join(out), flush=True)


@pytest.fixture(scope="session", autouse=True)
def hang_probe():
    real_send, real_handle, real_spawn = Session.send, Session._handle_message, BrowserProcess.spawn
    real_run = SessionRouter.run

    async def send(self, method, params=None, timeout=None):
        sent_at = time.monotonic()
        try:
            return await real_send(self, method, params, timeout)
        except TimeoutError as e:
            if "got no reply" in str(e):
                limit = self._router.default_timeout if timeout is None else timeout
                with contextlib.suppress(Exception):
                    await _report(self, method, sent_at, limit)
            raise

    async def handle(self, msg):
        _note(self._router, msg)
        return await real_handle(self, msg)

    async def spawn(self, *a, **kw):
        _procs.add(self)
        return await real_spawn(self, *a, **kw)

    async def run(self):
        self._probe_task = asyncio.current_task()
        return await real_run(self)

    Session.send, Session._handle_message, BrowserProcess.spawn = send, handle, spawn
    SessionRouter.run = run
    yield
    Session.send, Session._handle_message, BrowserProcess.spawn = real_send, real_handle, real_spawn
    SessionRouter.run = real_run


__all__ = ["hang_probe"]

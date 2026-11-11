"""Where tellurium and Chrome were when a command to Chrome got no reply.

Patched in for the integration tests by ``hang_probe`` (an autouse session
fixture): a command still unanswered after :func:`watch_after` seconds, well
inside its own deadline, makes a report while it is still pending (Chrome as
it hangs, not as the test's teardown leaves it):

* the chain of awaits of every asyncio task (``tests.await_chain``), taken
  the moment the watch fires;
* the messages Chrome sent on that pipe around the command, and whether
  Chrome still answers the root and the command's session;
* the process tree of that Chrome and where its browser process is
  (``tests.process_snapshot``), and the tail of Chrome's output.

The report goes to ``$TELLURIUM_HANG_REPORTS/<test>.txt`` (the CI uploads the
folder, red job or not), its path to the terminal. The first stall of a test
is reported in full, the next ones in a line; when the command ends, a line
says how. A command answered in time costs a timer; nothing in ``tellurium/``
changes.
"""

from __future__ import annotations

import asyncio
import collections
import math
import os
import re
import sys
import tempfile
import time
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tellurium.browser.process import BrowserProcess
from tellurium.cdp.transport._session import Session
from tests.await_chain import tasks_report
from tests.process_snapshot import snapshot
from tests.timeout_scale import scaled

#: Folder of the reports; a temporary one when unset.
ENV = "TELLURIUM_HANG_REPORTS"
#: A command still pending after this long is reported, stretched like Chrome's
#: answer waits (``tests.timeout_scale``: 30 s on the slow runners, past their
#: stalls of up to 27 s with nothing wrong)...
WATCH = 10.0
#: ...but before this share of its own deadline, so that it is still pending...
SHARE = 0.8
#: ...and before this when it has none (``Page.navigate`` inside a navigation,
#: bounded by ``Tab.get``'s 30 s, which is not stretched).
UNBOUNDED_WATCH = 20.0
#: Deadlines shorter than this are not watched: they are the tests' own, made
#: to expire on frozen pages; Chrome's waits are 10 s and longer.
MIN_LIMIT = 8.0
#: How long Chrome gets to answer the report's own commands.
LIVENESS_TIMEOUT = 5.0
#: Full reports in a session at most: a Chrome gone mute for good stalls every test after.
MAX_REPORTS = 20
#: Bytes of Chrome's output kept in a report.
OUTPUT_TAIL = 3000


@dataclass
class _State:
    test: str = "(before the first test)"
    test_started: float = 0.0
    report: Path | None = None
    full_reports: int = 0
    config: Any = None
    real_send: Any = None


_state = _State()
#: Every report written in this session, oldest first.
reports: list[Path] = []
_traffic: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_procs: weakref.WeakSet = weakref.WeakSet()
_T0 = time.monotonic()
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def watch_after(limit: float) -> float | None:
    """When a command with deadline *limit* is reported if still pending;
    ``None`` when it is not watched."""
    if limit < MIN_LIMIT:
        return None
    first = scaled(WATCH)
    if math.isinf(limit):
        return min(first, UNBOUNDED_WATCH)
    return min(first, SHARE * limit)


def begin_test(nodeid: str) -> None:
    """The test the next reports are about; its first stall gets a full report."""
    _state.test, _state.test_started, _state.report = nodeid, time.monotonic(), None


def report_dir() -> Path:
    folder = os.environ.get(ENV) or os.path.join(tempfile.gettempdir(), "tellurium-hang-reports")
    return Path(folder)


@contextmanager
def installed(config: Any = None) -> Iterator[None]:
    """The probe patched into ``Session`` and ``BrowserProcess`` for the body."""
    real_send, real_handle = Session.send, Session._handle_message
    real_spawn = BrowserProcess.spawn
    _state.config, _state.real_send = config, real_send

    async def send(self, method, params=None, timeout=None):
        limit = self._router.default_timeout if timeout is None else timeout
        after = watch_after(limit)
        if after is None:
            return await real_send(self, method, params, timeout)
        loop = asyncio.get_running_loop()
        sent_at = loop.time()
        made: list[asyncio.Task | None] = []

        def fire() -> None:
            made.append(_start_report(self, method, sent_at, limit))

        watch = loop.call_later(after, fire)
        outcome = "answered"
        try:
            return await real_send(self, method, params, timeout)
        except BaseException as exc:
            outcome = type(exc).__name__
            raise
        finally:
            watch.cancel()
            if made:
                await _end(made[0], method, outcome, loop.time() - sent_at)

    async def handle(self, msg):
        _note(self._router, msg)
        return await real_handle(self, msg)

    async def spawn(self, *args, **kwargs):
        _procs.add(self)
        return await real_spawn(self, *args, **kwargs)

    Session.send, Session._handle_message, BrowserProcess.spawn = send, handle, spawn
    try:
        yield
    finally:
        Session.send, Session._handle_message = real_send, real_handle
        BrowserProcess.spawn = real_spawn


@pytest.fixture(scope="session", autouse=True)
def hang_probe(pytestconfig):
    with installed(pytestconfig):
        yield


@pytest.fixture(autouse=True)
def hang_probe_test(request):
    begin_test(request.node.nodeid)
    yield
    begin_test(f"(after {request.node.nodeid})")


def _start_report(
    session: Session, method: str, sent_at: float, limit: float
) -> asyncio.Task | None:
    """The full report of the test's first stall as a task; a line for the next ones."""
    pending = asyncio.get_running_loop().time() - sent_at
    if _state.report is not None or _state.full_reports >= MAX_REPORTS:
        path = _state.report or _path_for(_state.test)
        _append(path, f"=== also pending for {pending:.1f}s: {method} (deadline {limit:g}s)\n")
        return None
    _state.full_reports += 1
    path = _state.report = _path_for(_state.test)
    tasks = tasks_report()  # now: where every task is as the watch fires
    _emit(f"HANG PROBE: {method} pending for {pending:.1f}s in {_state.test} -> {path}")
    return asyncio.get_running_loop().create_task(
        _safe_report(path, session, method, sent_at, limit, tasks), name="hang-probe-report"
    )


async def _end(report: asyncio.Task | None, method: str, outcome: str, took: float) -> None:
    """Wait for the report (Chrome is not closed before it is made), then note the end."""
    if report is not None:
        await asyncio.wait({report})
    path = _state.report or _path_for(_state.test)
    _append(path, f"=== end: {method} {outcome} after {took:.1f}s\n")


async def _safe_report(path: Path, *args: Any) -> None:
    try:
        text = await _report(*args)
    except Exception as exc:
        text = f"=== HANG PROBE failed: {exc!r}\n"
    await asyncio.to_thread(_append, path, text)
    reports.append(path)


async def _report(session: Session, method: str, sent_at: float, limit: float, tasks: str) -> str:
    router = session._router
    now = asyncio.get_running_loop().time()
    out = [
        f"=== HANG PROBE {_state.test}",
        f"{method} (session {(session.session_id or 'root')[:8]}) pending for "
        f"{now - sent_at:.1f}s, deadline {limit:g}s; test clock "
        f"{time.monotonic() - _state.test_started:.1f}s, run clock {time.monotonic() - _T0:.1f}s; "
        f"{sys.platform}",
    ]
    traffic = list(_traffic.get(router, ()))
    since = sum(1 for t, *_ in traffic if t >= sent_at)
    out.append(f"--- messages from Chrome on this pipe: {since} since the send; the last 25:")
    out.extend(f"  {t - sent_at:+8.2f}s {what} {sid}" for t, what, sid in traffic[-25:])

    proc = next((p for p in list(_procs) if p.transport is router._transport), None)
    pid = getattr(getattr(proc, "process", None), "pid", None)
    checks = [_check("root Browser.getVersion", router.root, "Browser.getVersion", {})]
    if session.session_id:
        expr = "[document.readyState, document.visibilityState, location.href]"
        params = {"expression": expr, "returnByValue": True}
        checks.append(_check("session Runtime.evaluate", session, "Runtime.evaluate", params))
    chrome = asyncio.to_thread(snapshot, pid) if pid is not None else _no_chrome()
    shot, *answers = await asyncio.gather(chrome, *checks)
    out.append("--- does Chrome answer?")
    out.extend(answers)
    out.append(f"--- Python tasks: {tasks}")
    out.append(f"--- Chrome {pid} (this pipe):" if pid is not None else "--- Chrome:")
    out.append(shot)
    output = getattr(proc, "_output", None)
    if output is not None:
        out.append(f"--- Chrome's output, the last {OUTPUT_TAIL} characters:")
        out.append(output.text()[-OUTPUT_TAIL:])
    return "\n".join(out) + "\n"


async def _no_chrome() -> str:
    return "no Chrome process for this pipe (none started by BrowserProcess)"


async def _check(label: str, session: Session, method: str, params: dict) -> str:
    started = time.monotonic()
    try:
        result = await _state.real_send(session, method, params, LIVENESS_TIMEOUT)
    except Exception as exc:
        return f"  {label}: {type(exc).__name__} after {time.monotonic() - started:.1f}s"
    return f"  {label}: ok in {time.monotonic() - started:.2f}s {str(result)[:200]}"


def _note(router: Any, msg: dict) -> None:
    seen = _traffic.get(router)
    if seen is None:
        seen = _traffic[router] = collections.deque(maxlen=200)
    what = msg.get("method") or f"reply {msg.get('id')}" + (" ERROR" if "error" in msg else "")
    seen.append((asyncio.get_running_loop().time(), what, (msg.get("sessionId") or "")[:8]))


def _path_for(test: str) -> Path:
    return report_dir() / f"{_UNSAFE.sub('_', test).strip('_')[-120:] or 'run'}.txt"


def _append(path: Path, text: str) -> None:
    """A few lines on a failure path: small enough to write from the loop."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def _emit(text: str) -> None:
    """To the terminal at once, past pytest's capture of the test's output."""
    config = _state.config
    if config is not None:
        capman = config.pluginmanager.getplugin("capturemanager")
        reporter = config.pluginmanager.getplugin("terminalreporter")
        if capman is not None and reporter is not None:
            with capman.global_and_fixture_disabled():
                reporter.write_line("")
                reporter.write_line(text)
            return
    print(text, file=sys.stderr, flush=True)


__all__ = ["hang_probe", "hang_probe_test"]

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
folder, red job or not; unset, a folder of this run), its path to the
terminal. It is written in sections, each on disk as soon as it is known: the
test may fail, and its loop close, right after the watch fires; the snapshot's
own thread writes it even then. The first stall of a test
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
import threading
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
#: How long a command that ended waits for its report still being made.
REPORT_WAIT = 20.0
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
_write_lock = threading.Lock()
#: Without the variable: read once, before any test points ``tempfile`` elsewhere.
_RUN_DIR = Path(tempfile.gettempdir(), "tellurium-hang-reports", f"{time.time_ns()}-{os.getpid()}")
_NO_CHROME = "no Chrome process for this pipe (none started by BrowserProcess)"


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
    """``$TELLURIUM_HANG_REPORTS``, else a folder of this run alone."""
    folder = os.environ.get(ENV)
    return Path(folder) if folder else _RUN_DIR


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
    """The full report of the test's first stall, a line for the next ones.

    What is known now (the stall, Chrome's traffic, every task's awaits,
    Chrome's output) goes to disk at once, in a file of its own: the test may
    fail, and its loop close, right after. Chrome's snapshot and whether it
    answers follow as they come (``_rest``)."""
    pending = asyncio.get_running_loop().time() - sent_at
    if _state.report is not None or _state.full_reports >= MAX_REPORTS:
        path = _state.report or _path_for(_state.test)
        _append(path, f"=== also pending for {pending:.1f}s: {method} (deadline {limit:g}s)\n")
        return None
    _state.full_reports += 1
    path = _state.report = _path_for(_state.test)
    tasks = tasks_report()  # now: where every task is as the watch fires
    proc = next((p for p in list(_procs) if p.transport is session._router._transport), None)
    _append(path, _head(session, method, sent_at, limit, tasks, proc), fresh=True)
    reports.append(path)
    _emit(f"HANG PROBE: {method} pending for {pending:.1f}s in {_state.test} -> {path}")
    pid = getattr(getattr(proc, "process", None), "pid", None)
    return asyncio.get_running_loop().create_task(
        _rest(path, session, pid), name="hang-probe-report"
    )


async def _end(report: asyncio.Task | None, method: str, outcome: str, took: float) -> None:
    """Wait a while for the report (Chrome is not closed before it is made),
    then note the end, even if this wait is cut short."""
    path = _state.report or _path_for(_state.test)
    late = ""
    try:
        if report is not None:
            await asyncio.wait({report}, timeout=REPORT_WAIT)
            late = "" if report.done() else " (the report is still being made)"
    finally:
        _append(path, f"=== end: {method} {outcome} after {took:.1f}s{late}\n")


def _head(
    session: Session, method: str, sent_at: float, limit: float, tasks: str, proc: Any
) -> str:
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
    out.append(f"--- Python tasks: {tasks}")
    output = getattr(proc, "_output", None)
    if output is not None:
        out.append(f"--- Chrome's output, the last {OUTPUT_TAIL} characters:")
        out.append(output.text()[-OUTPUT_TAIL:])
    return "\n".join(out) + "\n"


async def _rest(path: Path, session: Session, pid: int | None) -> None:
    """Chrome's snapshot (written by its own thread, which a closing loop does
    not stop) and whether Chrome answers; a cut-short part says so."""
    if pid is None:
        _append(path, f"--- Chrome:\n{_NO_CHROME}\n")
        shot = None
    else:
        shot = asyncio.ensure_future(asyncio.to_thread(_snapshot_into, path, pid))
    checks = [_check("root Browser.getVersion", session._router.root, "Browser.getVersion", {})]
    if session.session_id:
        expr = "[document.readyState, document.visibilityState, location.href]"
        params = {"expression": expr, "returnByValue": True}
        checks.append(_check("session Runtime.evaluate", session, "Runtime.evaluate", params))
    try:
        answers = await asyncio.gather(*checks)
    except BaseException as exc:
        _append(path, f"--- does Chrome answer? cut short: {type(exc).__name__}\n")
        raise
    _append(path, "--- does Chrome answer?\n" + "\n".join(answers) + "\n")
    if shot is not None:
        await shot


def _snapshot_into(path: Path, pid: int) -> None:
    try:
        text = snapshot(pid)
    except Exception as exc:  # noqa: BLE001 — the report says it, the test goes on
        text = f"snapshot failed: {exc!r}"
    _append(path, f"--- Chrome {pid} (this pipe):\n{text}\n")


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


def _append(path: Path, text: str, fresh: bool = False) -> None:
    """A section of a report, on disk when this returns (the loop's and the
    snapshot thread's alike); *fresh* starts the file anew. A few lines on a
    failure path: small enough to write from the loop."""
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w" if fresh else "a", encoding="utf-8") as f:
            f.write(text)
            f.flush()


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

"""Every stall of the runner during an integration session, with its test.

The hang probe reports a command Chrome left unanswered; a runner that stops
(a shadow copy freezing the volume on Windows, R4-B) also slows launches,
closes and waits that send no command, and leaves nothing. With
``$TELLURIUM_HANG_REPORTS`` set (the CI), a :class:`~tests.runner_stall.Canary`
beats for the whole session and each beat :data:`OVER` seconds late or more
goes to :data:`FILE` in that folder: when, how long, during which test. On
Windows the shadow copy events of the session follow at the end, read by
``wevtutil`` (:mod:`tests.shadow_copy_events`). Comparing two sets of runs
(the shadow copy service stopped or not) is counting these lines.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import UTC, datetime

import pytest

from tests.runner_stall import Canary

#: The file, in ``$TELLURIUM_HANG_REPORTS``.
FILE = "runner-stalls.txt"
#: Least lateness of a beat written down, in seconds.
OVER = 2.0


class StallLog:
    """The stalls of this session, written as they end."""

    def __init__(self, folder: str, windows: bool = sys.platform == "win32") -> None:
        self.test = "(between tests)"
        self._path = os.path.join(folder, FILE)
        self._windows = windows
        self._start = time.time()
        self._lock = threading.Lock()
        os.makedirs(folder, exist_ok=True)
        self._write(f"session from {_iso(self._start)} (pid {os.getpid()})\n")

    def stalled(self, late: float, since: float) -> None:
        self._write(f"stall {late:.1f} s from {_iso(since)} during {self.test}\n")

    def close(self) -> None:
        end = time.time()
        text = f"session to {_iso(end)}\n"
        if self._windows:
            text += "shadow copy events of the session:\n"
            text += _shadow_copies(end - self._start + 60) + "\n"
        self._write(text)

    def _write(self, text: str) -> None:
        with self._lock, open(self._path, "a", encoding="utf-8") as f:
            f.write(text)


def _iso(moment: float) -> str:
    return datetime.fromtimestamp(moment, UTC).isoformat(timespec="milliseconds")


def _shadow_copies(window: float) -> str:
    from tests.shadow_copy_events import Events

    events = Events(window)
    return "\n".join(filter(None, [events.read(), events.read_missed()]))


_log: StallLog | None = None


@pytest.fixture(scope="session", autouse=True)
def runner_stall_log():
    """The session's :class:`StallLog`, when the CI asks for reports."""
    global _log
    folder = os.environ.get("TELLURIUM_HANG_REPORTS")
    if not folder:
        yield None
        return
    _log = StallLog(folder)
    try:
        with Canary(on_stall=_log.stalled, over=OVER):
            yield _log
    finally:
        _log.close()
        _log = None


@pytest.fixture(autouse=True)
def runner_stall_test(request):
    """Names the running test in the log."""
    if _log is not None:
        _log.test = request.node.nodeid
    yield
    if _log is not None:
        _log.test = f"(after {request.node.nodeid})"


__all__ = ["FILE", "OVER", "StallLog", "runner_stall_log", "runner_stall_test"]

"""The C stress of macOS's rwlock never outlives its test: a program that goes
silent (a final join that never ends) or stalls fails with its snapshot and
is ended."""

from __future__ import annotations

import os
import sys
import time

import pytest

from tests.integration import rwlock_stress

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="select on a pipe")


def _program(body: str) -> list[str]:
    return [sys.executable, "-c", f"import sys, time\n{body}"]


@pytest.fixture
def reported(monkeypatch):
    pids: list[int] = []
    monkeypatch.setattr(rwlock_stress, "_report", lambda pid: pids.append(pid) or "a snapshot")
    return pids


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_a_silent_program_fails_at_its_deadline_and_is_ended(reported):
    started = time.monotonic()
    with pytest.raises(pytest.fail.Exception, match="no word in 1s"):
        rwlock_stress._outcome(_program("time.sleep(60)"), deadline=1.0)
    assert time.monotonic() - started < 15
    [pid] = reported
    assert _gone(pid)


def test_a_stall_fails_with_the_snapshot_and_is_ended(reported):
    body = "print('STALL after 7 sections', flush=True); time.sleep(60)"
    with pytest.raises(pytest.fail.Exception, match="STALL after 7 sections"):
        rwlock_stress._outcome(_program(body), deadline=10.0)
    [pid] = reported
    assert _gone(pid)


def test_a_program_that_ends_well_says_so(reported):
    assert rwlock_stress._outcome(_program("print('ok 9 sections')"), 10.0) == "ok 9 sections"
    assert reported == []

"""The canary that measures how long the runner could not write (R4-D)."""

from __future__ import annotations

import time

from tests import runner_stall


def test_a_quiet_runner_shows_no_stall():
    with runner_stall.Canary() as canary:
        time.sleep(1.0)
    assert canary.stall < 0.5


def test_a_held_write_shows_as_a_stall(monkeypatch):
    real = runner_stall.os.fsync
    held = []

    def fsync(fd):
        if not held:
            held.append(fd)
            time.sleep(1.5)  # a shadow copy holds the write
        real(fd)

    monkeypatch.setattr(runner_stall.os, "fsync", fsync)
    with runner_stall.Canary() as canary:
        time.sleep(2.5)
    assert 1.2 < canary.stall < 2.5


def test_a_write_still_held_at_the_end_counts(monkeypatch):
    monkeypatch.setattr(runner_stall.os, "fsync", lambda fd: time.sleep(3.0))
    with runner_stall.Canary() as canary:
        time.sleep(1.5)
    assert canary.stall > 1.0


def test_each_stall_over_the_mark_is_told_with_its_moment(monkeypatch):
    real = runner_stall.os.fsync
    held, told = [], []

    def fsync(fd):
        if not held:
            held.append(time.time())
            time.sleep(1.5)
        real(fd)

    monkeypatch.setattr(runner_stall.os, "fsync", fsync)
    with runner_stall.Canary(on_stall=lambda late, since: told.append((late, since)), over=1.0):
        time.sleep(2.5)
    assert len(told) == 1
    late, since = told[0]
    assert 1.2 < late < 2.5
    assert abs(since - held[0]) < 0.6  # when the held beat was due


def test_the_stall_log_names_the_test_and_the_shadow_copies(tmp_path, monkeypatch):
    from tests import stall_log

    events = []
    monkeypatch.setattr(stall_log, "_shadow_copies", lambda window: events.append(window) or "  ev")
    log = stall_log.StallLog(str(tmp_path), windows=True)
    log.test = "tests/integration/test_x.py::test_y"
    log.stalled(12.25, 1_700_000_000.0)
    log.close()
    text = (tmp_path / stall_log.FILE).read_text()
    assert "stall 12.2 s from 2023-11-14T22:13:20" in text
    assert "during tests/integration/test_x.py::test_y" in text
    assert "shadow copy events of the session:\n  ev" in text
    assert events and events[0] > 0

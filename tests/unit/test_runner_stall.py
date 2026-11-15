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

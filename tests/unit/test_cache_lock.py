"""The cache's install lock: readers sharing it never starve an install."""

from __future__ import annotations

import sys
import threading
import time

import pytest

from tellurium.browser import _cache


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no shared lock")
def test_readers_taking_turns_do_not_starve_a_waiting_install(tmp_path):
    """Two readers whose holds overlap keep the lock shared without pause:
    an install asking for it exclusive must still get in, because no new
    reader enters while it waits."""
    root = tmp_path / "cache"
    root.mkdir()
    stop = threading.Event()
    errors: list[BaseException] = []

    def reader(offset: float) -> None:
        time.sleep(offset)
        try:
            while not stop.is_set():
                with _cache.reading_lock(root):
                    time.sleep(0.1)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    readers = [threading.Thread(target=reader, args=(o,)) for o in (0.0, 0.05)]
    for t in readers:
        t.start()
    time.sleep(0.2)  # both readers are taking turns now
    entered = threading.Event()

    def install() -> None:
        with _cache.install_lock(root):
            entered.set()

    writer = threading.Thread(target=install)
    start = time.monotonic()
    writer.start()
    try:
        assert entered.wait(3), "the install never got the lock"
        assert time.monotonic() - start < 1.0
    finally:
        stop.set()
        writer.join(5)
        for t in readers:
            t.join(5)
    assert not errors


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no shared lock")
def test_readers_still_share_the_lock(tmp_path):
    """The gate makes readers queue only for an instant: two of them hold
    the lock at the same time."""
    root = tmp_path / "cache"
    root.mkdir()
    with _cache.reading_lock(root):
        inside = threading.Event()

        def other() -> None:
            with _cache.reading_lock(root):
                inside.set()

        t = threading.Thread(target=other)
        t.start()
        assert inside.wait(2)
        t.join(2)


def test_a_reader_waits_for_an_install_in_progress(tmp_path):
    root = tmp_path / "cache"
    root.mkdir()
    held, release = threading.Event(), threading.Event()

    def hold() -> None:
        with _cache.install_lock(root):
            held.set()
            release.wait(5)

    t = threading.Thread(target=hold)
    t.start()
    assert held.wait(5)
    entered = threading.Event()

    def read() -> None:
        with _cache.reading_lock(root):
            entered.set()

    r = threading.Thread(target=read)
    r.start()
    try:
        assert not entered.wait(0.3)
    finally:
        release.set()
    assert entered.wait(2)
    t.join(2)
    r.join(2)

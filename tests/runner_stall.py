"""How long the runner could not write to its disk while a test timed something.

A shadow copy freezes the writes to a Windows runner's volume, and with them
Chrome, for ~25 s and up to ~60 s (R4-B, ``docs/gotchas.md``). A test that
bounds how long Chrome takes can subtract what the runner itself lost: a
thread writes and syncs a small file every :data:`BEAT` seconds, and
:attr:`Canary.stall` is the longest a beat took past its due (a write held,
or the thread not scheduled). It measures the runner, not Chrome: a Chrome
slow on its own leaves it near zero. With *on_stall*, each beat late by
*over* seconds or more is told as it ends (:mod:`tests.stall_log`).
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from collections.abc import Callable
from types import TracebackType

#: Seconds between two beats.
BEAT = 0.25


class Canary:
    """``with Canary() as canary:`` then :attr:`stall` (seconds)."""

    def __init__(
        self,
        folder: str | None = None,
        on_stall: Callable[[float, float], None] | None = None,
        over: float = 2.0,
        sync: Callable[[int], None] | None = None,
    ) -> None:
        """*on_stall(late, since)*: a beat *late* seconds past its due, due at
        the wall-clock time *since*; called from the canary's thread. *sync*
        (``os.fsync`` by default) flushes each beat: a test holds its own
        canary's writes with it, not every canary's in the process."""
        self._folder = folder or tempfile.gettempdir()
        self._sync = sync or os.fsync
        self._on_stall = on_stall
        self._over = over
        self._done = threading.Event()
        self._stall = 0.0
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._beat, name="runner-stall-canary", daemon=True)
        self._last = 0.0

    @property
    def stall(self) -> float:
        """The longest beat past its due so far, the one still pending included."""
        with self._lock:
            pending = time.monotonic() - self._last - BEAT if self._last else 0.0
            return max(self._stall, pending, 0.0)

    def __enter__(self) -> Canary:
        self._last = time.monotonic()
        self._thread.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        stall = self.stall  # a beat held now counts
        self._done.set()
        self._thread.join(BEAT * 4)
        with self._lock:
            self._stall = max(self._stall, stall)

    def _beat(self) -> None:
        fd, path = tempfile.mkstemp(prefix="canary-", dir=self._folder)
        try:
            while not self._done.wait(BEAT):
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, str(time.time()).encode())
                self._sync(fd)
                now = time.monotonic()
                with self._lock:
                    late = now - self._last - BEAT
                    self._stall = max(self._stall, late)
                    self._last = now
                if self._on_stall is not None and late >= self._over:
                    self._on_stall(late, time.time() - late)
        finally:
            os.close(fd)
            try:
                os.unlink(path)
            except OSError:
                pass


__all__ = ["BEAT", "Canary"]

"""The browser slots of a SessionPool, shared by every event loop and thread.

An ``asyncio.Semaphore`` belongs to one loop: a pool used by one
``asyncio.run`` after another, or by loops running at once in threads, needs a
cap that holds across them. :class:`Slots` counts under a ``threading.Lock``;
a coroutine waiting for one polls (never blocking its loop), can be cancelled
while it waits, and takes nothing then.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

#: Seconds between two looks at the count while every slot is taken.
POLL = 0.01


class Slots:
    """At most *total* held at once, whatever loop or thread holds them."""

    def __init__(self, total: int) -> None:
        self.total = total
        self._held = 0
        self._lock = threading.Lock()

    @property
    def held(self) -> int:
        return self._held

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """One slot, from when it is free until the block ends (on error and
        cancellation too)."""
        while not self._take():
            await asyncio.sleep(POLL)
        try:
            yield
        finally:
            with self._lock:
                self._held -= 1

    def _take(self) -> bool:
        with self._lock:
            if self._held >= self.total:
                return False
            self._held += 1
            return True

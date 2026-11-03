"""The browser slots of a SessionPool, shared by every event loop and thread.

An ``asyncio.Semaphore`` belongs to one loop: a pool used by one
``asyncio.run`` after another, or by loops running at once in threads, needs a
cap that holds across them. :class:`Slots` counts under a ``threading.Lock``
and hands slots out first come, first served: whoever finds them all taken
joins a queue with a future of its own loop, and whoever leaves gives its
slot straight to the head of the queue (waking it with
``call_soon_threadsafe``), so nobody polls and a waiter cannot lose its turn
to a task that releases and asks again. A waiter cancelled in the queue
leaves it; one cancelled after the slot was given to it, before it resumed,
passes the slot on: no slot is ever lost. Not even when the waiter's loop
is stopped when the slot is given, then closed without cancelling the task
(a loop driven by hand, not ``asyncio.run``): the wake-up never runs there,
and the next caller that finds no slot free takes the slot back from the
closed loop and hands it on.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class _Waiter:
    """One coroutine in the queue: its loop, the future it awaits, and
    whether a slot was handed to it (read and written under the lock)."""

    __slots__ = ("future", "given", "loop")

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.future: asyncio.Future[None] = loop.create_future()
        self.given = False


class Slots:
    """At most *total* held at once, whatever loop or thread holds them,
    given in the order they were asked for."""

    def __init__(self, total: int) -> None:
        self._total = total
        self._held = 0
        self._queue: deque[_Waiter] = deque()
        self._given: set[_Waiter] = set()  # handed a slot, not resumed yet
        self._lock = threading.Lock()

    @property
    def total(self) -> int:
        """The cap, fixed at creation (raising it would wake nobody queued)."""
        return self._total

    @property
    def held(self) -> int:
        """Slots taken now, including those given to a waiter not yet resumed."""
        return self._held

    @property
    def waiting(self) -> int:
        """Coroutines in the queue."""
        return len(self._queue)

    @asynccontextmanager
    async def slot(self, timeout: float | None = None) -> AsyncIterator[None]:
        """One slot, from when it is this caller's turn until the block ends
        (on error and cancellation too). *timeout* (seconds) limits only the
        wait: past it, :class:`TimeoutError`, with no slot taken and no place
        left in the queue; the block itself runs as long as it needs. A
        cancellation during the wait gives up the place the same way."""
        await self._take(timeout)
        try:
            yield
        finally:
            self._give_back()

    async def _take(self, timeout: float | None) -> None:
        with self._lock:
            self._reclaim()
            if self._held < self._total and not self._queue:
                self._held += 1
                return
            waiter = _Waiter(asyncio.get_running_loop())
            self._queue.append(waiter)
        try:
            if timeout is None:
                await waiter.future
            else:
                await asyncio.wait_for(waiter.future, timeout)
        except BaseException as exc:
            with self._lock:
                given = waiter.given
                self._given.discard(waiter)
                if not given and waiter in self._queue:
                    self._queue.remove(waiter)
            if given:  # handed over, but this task will not use it: the next one will
                self._give_back()
            if isinstance(exc, asyncio.TimeoutError):  # a distinct class before 3.11
                raise TimeoutError(f"no slot free within {timeout} s") from None
            raise
        with self._lock:
            self._given.discard(waiter)

    def _give_back(self) -> None:
        with self._lock:
            self._hand_on()

    def _hand_on(self) -> None:
        """Under the lock: hand a slot to the head of the queue, else free it."""
        while self._queue:
            waiter = self._queue.popleft()
            try:
                waiter.loop.call_soon_threadsafe(_wake, waiter.future)
            except RuntimeError:  # its loop is closed: it will never take it
                continue
            waiter.given = True
            self._given.add(waiter)
            return
        self._held -= 1

    def _reclaim(self) -> None:
        """Under the lock: a slot handed to a waiter whose loop has been
        closed since (its wake-up dropped, its task never to run again) is
        handed on. Its task, if collected later, gives nothing back."""
        for waiter in [w for w in self._given if w.loop.is_closed()]:
            self._given.discard(waiter)
            waiter.given = False
            self._hand_on()


def _wake(future: asyncio.Future[None]) -> None:
    if not future.done():  # cancelled meanwhile: the waiter passes the slot on
        future.set_result(None)

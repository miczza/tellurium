"""Pool — the places of the multiplexer, the queue of clients and the warm Chromes.

At most *size* clients hold a place at once; the others wait in a first come,
first served queue (:class:`~tellurium.session.slots.Slots`) up to
*acquire_timeout* seconds. Each client gets a place of its own and leaves
with its Chrome: the place launches the next one only if it is wanted warm.
*warm* places with no client keep a Chrome ready (fewer when clients hold
the others). Proxies are handed out in turn, one per launch.
"""

from __future__ import annotations

import asyncio
import itertools
from contextlib import AsyncExitStack
from typing import Any

from tellurium.multiplexer.health import HANG
from tellurium.multiplexer.place import Place, PlaceClosed
from tellurium.multiplexer.relay import Relay
from tellurium.session.slots import Slots

#: Seconds a client that got its place waits for a Chrome to be ready there.
LAUNCH_WAIT = 60.0
#: Clients that may wait in the queue; past it a new one is turned away at once.
MAX_QUEUE = 64

_PREFERENCE = {"ready": 0, "launching": 1, "failing": 2, "idle": 3}


class QueueTimeout(Exception):
    """No place freed up within the acquire timeout."""


class NoChrome(Exception):
    """A place was free, but no Chrome could be launched there in time."""


class PoolClosed(Exception):
    """The pool is shutting down."""


class ClientGone(Exception):
    """The client went away while it waited."""


class Lease:
    """A client's place and the relay of its Chrome; :meth:`release` gives both back."""

    def __init__(self, stack: AsyncExitStack, place: Place, relay: Relay) -> None:
        self._stack = stack
        self.place = place
        self.relay = relay

    async def release(self) -> None:
        """Close the Chrome, then free the place for the queue. Idempotent."""
        await self._stack.aclose()


class Pool:
    def __init__(
        self,
        size: int,
        *,
        proxies: tuple[str, ...],
        warm: int,
        acquire_timeout: float,
        launch: dict[str, Any],
    ) -> None:
        self.size = size
        self.warm = warm
        self.acquire_timeout = acquire_timeout
        self.launch = launch
        self._proxies = itertools.cycle(proxies) if proxies else None
        self._slots = Slots(size)
        self.places: list[Place] = []
        self._closing: asyncio.Future[None] | None = None
        self.version: dict | None = None
        self._version_known: asyncio.Event | None = None
        self._version_asked = False  # someone waits for the version: warm one place
        self.connections = 0
        self.crashes = 0
        self.hangs = 0
        self.launch_failures = 0

    # ------------------------------------------------------------------ #
    # Life
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._closing = loop.create_future()
        self._version_known = asyncio.Event()
        if self.version is not None:
            self._version_known.set()
        self.places = [Place(self, i) for i in range(self.size)]
        for place in self.places:
            place.start()
        self.rebalance()

    def stop_accepting(self) -> None:
        """Clients still in the queue, or waiting for a Chrome, are turned away."""
        if self._closing is not None and not self._closing.done():
            self._closing.set_result(None)

    async def close(self) -> None:
        """Close every place, Chrome and relay; bounded, safe to call twice."""
        self.stop_accepting()
        places, self.places = self.places, []
        if places:
            await asyncio.gather(*(place.close() for place in places), return_exceptions=True)

    # ------------------------------------------------------------------ #
    # Clients
    # ------------------------------------------------------------------ #

    async def acquire(self, gone: asyncio.Future | None = None) -> Lease:
        """A place and a ready Chrome for one client.

        Raises :class:`QueueTimeout` past *acquire_timeout* in the queue (or at
        once with :data:`MAX_QUEUE` clients waiting), :class:`NoChrome` when no
        Chrome could be launched within :data:`LAUNCH_WAIT`, :class:`PoolClosed`
        on shutdown, and :class:`ClientGone` as soon as *gone* resolves (the
        client hung up): it leaves the queue, and no Chrome is launched for it.
        """
        if self._slots.held >= self.size and self._slots.waiting >= MAX_QUEUE:
            raise QueueTimeout(f"{MAX_QUEUE} clients are already waiting")
        stack = AsyncExitStack()
        try:
            try:
                slot = self._slots.slot(timeout=self.acquire_timeout)
                await self._unless_closing(stack.enter_async_context(slot), gone)
            except TimeoutError:
                raise QueueTimeout(
                    f"all {self.size} Chromes stayed busy for {self.acquire_timeout:g} s"
                ) from None
            place = self._pick()
            try:
                ready = place.claim()
            except PlaceClosed as exc:
                raise PoolClosed(str(exc)) from None
            stack.push_async_callback(place.release)
            self.rebalance()
            try:
                relay = await self._unless_closing(
                    asyncio.wait_for(asyncio.shield(ready), LAUNCH_WAIT), gone
                )
            except TimeoutError:
                raise NoChrome(
                    f"no Chrome could be launched in {LAUNCH_WAIT:g} s: {place.error or 'no error'}"
                ) from None
            except PlaceClosed as exc:
                raise PoolClosed(str(exc)) from None
        except BaseException:
            await stack.aclose()
            raise
        self.connections += 1
        return Lease(stack, place, relay)

    async def _unless_closing(self, awaitable: Any, gone: asyncio.Future | None = None) -> Any:
        """*awaitable*'s result, unless the pool starts closing or *gone*
        resolves first."""
        if self._closing is None or self._closing.done() or (gone is not None and gone.done()):
            if asyncio.iscoroutine(awaitable):
                awaitable.close()
            if gone is not None and gone.done():
                raise ClientGone("the client hung up")
            raise PoolClosed("the multiplexer is shutting down")
        task = asyncio.ensure_future(awaitable)
        stops = [self._closing] if gone is None else [self._closing, gone]
        try:
            await asyncio.wait([task, *stops], return_when=asyncio.FIRST_COMPLETED)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.wait([task])
        if task.cancelled():
            if gone is not None and gone.done():
                raise ClientGone("the client hung up")
            raise PoolClosed("the multiplexer is shutting down")
        return task.result()

    def _pick(self) -> Place:
        """A place with no client: one with a ready Chrome first.

        There always is one: a client holds a place only while it holds a slot.
        """
        free = [p for p in self.places if not p.claimed]
        if not free:
            raise PoolClosed("the multiplexer is shutting down")
        return min(free, key=lambda p: _PREFERENCE.get(p.state, 4))

    # ------------------------------------------------------------------ #
    # Warm places, proxies, versions, counters (called by the places)
    # ------------------------------------------------------------------ #

    def rebalance(self, idle: Place | None = None) -> None:
        """Keep *warm* places with no client wanted (fewer if clients hold the rest).

        *idle* just closed its Chrome: it stops being warm if enough others are.
        """
        free = [p for p in self.places if not p.claimed]
        target = min(self.warm, len(free))
        if self.version is None and not any(p.warm for p in free) and self._version_asked:
            target = max(target, 1)
        warm = [p for p in free if p.warm and p is not idle]
        if idle is not None and idle.warm:
            if len(warm) >= target:
                idle.warm = False
            else:
                warm.append(idle)
        for place in sorted(free, key=lambda p: _PREFERENCE.get(p.state, 4)):
            if len(warm) >= target:
                break
            if not place.warm:
                place.want()
                warm.append(place)

    async def browser_version(self, timeout: float) -> dict:
        """What ``Browser.getVersion`` answers, from the first Chrome that ran.

        With no Chrome launched yet, one place is warmed up to learn it.
        Raises :class:`TimeoutError` when none answers within *timeout*.
        """
        if self.version is not None:
            return self.version
        assert self._version_known is not None
        self._version_asked = True
        self.rebalance()
        try:
            await self._unless_closing(asyncio.wait_for(self._version_known.wait(), timeout))
        except TimeoutError:
            raise TimeoutError("no Chrome could be launched to read its version") from None
        assert self.version is not None
        return self.version

    def learn_version(self, version: dict) -> None:
        if self.version is None and version:
            self.version = version
            if self._version_known is not None:
                self._version_known.set()

    def next_proxy(self) -> str | None:
        return next(self._proxies) if self._proxies is not None else None

    def count_loss(self, kind: str) -> None:
        if kind == HANG:
            self.hangs += 1
        else:
            self.crashes += 1

    def status(self) -> dict:
        return {
            "size": self.size,
            "warm": self.warm,
            "clients": sum(p.claimed for p in self.places),
            "queue": self._slots.waiting,
            "connections": self.connections,
            "crashes": self.crashes,
            "hangs": self.hangs,
            "launch_failures": self.launch_failures,
            "slots": [p.status() for p in self.places],
        }

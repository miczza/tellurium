"""Place — one seat of the pool, and the life of the Chrome sitting in it.

A place's own task is the only one that launches and closes its Chromes: a
client *claims* the place, borrows the :class:`Relay` of its Chrome, and
*releases* it when it leaves; the task then closes that Chrome with its
profile and, if the place is wanted warm, launches the next one (new seed,
next proxy). While a Chrome lives, :func:`health.watch` probes it; a crash or
a hang closes the client's WebSocket with 1011 and the reason, and the
Chrome is killed and replaced. A failed launch does not take the place: it
is retried with a growing pause while the place is wanted, and the error
shows in the status.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import secrets
import signal
import time
from typing import TYPE_CHECKING, Any

from tellurium.browser.raw_chrome import RawChrome
from tellurium.multiplexer import health
from tellurium.multiplexer.relay import (
    CLOSE_ERROR,
    CLOSE_GOING_AWAY,
    CLOSE_NORMAL,
    Relay,
    RelayClosed,
)

if TYPE_CHECKING:
    from tellurium.multiplexer.pool import Pool

#: Pause after the first failed launch, doubled at each failure up to the cap.
BACKOFF_FIRST = 1.0
BACKOFF_CAP = 30.0

#: Close code and reason when the server restarts a place on request.
CLOSE_RESTART = 1012


class PlaceClosed(Exception):
    """The pool is closing: the place will not give a Chrome any more."""


class Place:
    """One seat of the pool: at most one Chrome, at most one client."""

    def __init__(self, pool: Pool, index: int) -> None:
        self.id = index
        self._pool = pool
        self.state = "idle"
        self.claimed = False
        self.warm = False
        self.chrome: RawChrome | None = None
        self.relay: Relay | None = None
        self.started: float | None = None  # monotonic time the Chrome was ready
        self.launches = 0
        self.restarts = 0
        self.failures = 0  # launch failures in a row
        self.error: str | None = None
        self._wanted = asyncio.Event()
        self._changed = asyncio.Event()  # claim, release, restart: wakes the task
        self._ready: asyncio.Future[Relay] | None = None
        self._left = False  # the client released the place
        self._attached = False  # the client got the relay of the current Chrome
        self._restart = False
        self._idle = asyncio.Event()
        self._idle.set()
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ #
    # Driven by the pool and its clients
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._task = asyncio.ensure_future(self._run())

    def want(self) -> None:
        """Have a Chrome ready here (warm) even with no client."""
        self.warm = True
        self._wanted.set()

    def claim(self) -> asyncio.Future[Relay]:
        """Take this place for one client, at once: the future gets the relay of
        a ready Chrome (after a launch if none is ready yet)."""
        if self._task is None or self._task.done():
            raise PlaceClosed("the multiplexer is shutting down")
        self.claimed, self.warm, self._left, self._attached = True, False, False, False
        self._idle.clear()
        self._ready = asyncio.get_running_loop().create_future()
        self._wanted.set()
        self._changed.set()
        return self._ready

    async def release(self) -> None:
        """The client is done: returns once its Chrome is closed."""
        if not self.claimed:
            return
        self._left = True
        self._changed.set()
        if self._task is None or self._task.done():
            self._unclaim()
            return
        await self._idle.wait()

    def restart(self) -> None:
        """Replace the Chrome of this place now (its client gets 1012)."""
        if self.chrome is not None:
            self._restart = True
            self._changed.set()

    async def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.wait([task])

    # ------------------------------------------------------------------ #
    # The place's own task
    # ------------------------------------------------------------------ #

    async def _run(self) -> None:
        try:
            while True:
                await self._wanted.wait()
                relay = await self._launch()
                if relay is not None:
                    await self._live(relay)
                if self.claimed and (self._attached or self._left):
                    await self._wait(lambda: self._left)
                    self._unclaim()
                if not self.claimed and not self.warm:
                    self._wanted.clear()
                self._pool.rebalance(self)
        finally:
            self._fail_claim(PlaceClosed("the multiplexer is shutting down"))
            self._unclaim()
            self.state = "closed"

    def _unclaim(self) -> None:
        self.claimed = self._attached = False
        self._ready = None
        self._idle.set()

    def _fail_claim(self, error: Exception) -> None:
        if self._ready is not None and not self._ready.done():
            self._ready.set_exception(error)
            self._ready.exception()  # retrieved: the claimer may be gone already

    def _wanted_now(self) -> bool:
        return self.warm or (self.claimed and not self._left)

    async def _wait(self, condition: Any, timeout: float | None = None) -> None:
        """Until *condition()* holds (re-checked at each change) or *timeout*."""
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout
        while not condition():
            left = None if deadline is None else deadline - loop.time()
            if left is not None and left <= 0:
                return
            self._changed.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._changed.wait(), left)

    async def _launch(self) -> Relay | None:
        """A ready Chrome and its relay, retrying while the place is wanted."""
        pause = BACKOFF_FIRST
        while self._wanted_now():
            self.state = "launching"
            proxy, seed = self._pool.next_proxy(), secrets.randbits(31)
            self._restart = False
            try:
                chrome = await RawChrome.launch(**self._pool.launch, proxy=proxy, seed=seed)
            except Exception as exc:  # noqa: BLE001 - reported in the status, then retried
                self.failures += 1
                self.error = f"{type(exc).__name__}: {exc}"[:500]
                self._pool.launch_failures += 1
                self.state = "failing"
                await self._wait(lambda: not self._wanted_now(), pause)
                pause = min(pause * 2, BACKOFF_CAP)
                continue
            relay = await self._open(chrome)
            if relay is not None:
                return relay
        self.state = "idle"
        return None

    async def _open(self, chrome: RawChrome) -> Relay | None:
        """Start the relay and read the version; None (Chrome closed) if it fails."""
        self.chrome, self.launches = chrome, self.launches + 1
        relay = None
        try:
            relay = self.relay = Relay(chrome.transport)
            relay.start()
            self._pool.learn_version(await relay.probe(health.TIMEOUT))
        except (TimeoutError, RelayClosed) as exc:
            self.failures += 1
            self.error = f"Chrome did not answer after its launch: {exc}"
            self._pool.launch_failures += 1
            await self._shut(CLOSE_ERROR, "Chrome failed", kill=True)
            return None
        except BaseException:
            await self._shut(CLOSE_GOING_AWAY, "the multiplexer is shutting down", kill=False)
            raise
        self.failures, self.error = 0, None
        self.started = time.monotonic()
        return relay

    async def _live(self, relay: Relay) -> None:
        """From a ready Chrome to a closed one."""
        assert self.chrome is not None
        watch = asyncio.ensure_future(health.watch(relay, self.chrome))
        code, reason, kill = CLOSE_GOING_AWAY, "the multiplexer is shutting down", False
        try:
            gone = False
            while not gone:
                self.state = "busy" if self.claimed else "ready"
                if self.claimed and self._ready is not None and not self._ready.done():
                    self._ready.set_result(relay)
                    self._attached = True
                if self._left:
                    code, reason = CLOSE_NORMAL, "the client left"
                    break
                if self._restart:
                    self._restart = False
                    self.restarts += 1
                    code, reason, kill = CLOSE_RESTART, "Chrome restarted by the server", True
                    break
                self._changed.clear()
                changed = asyncio.ensure_future(self._changed.wait())
                try:
                    await asyncio.wait([watch, changed], return_when=asyncio.FIRST_COMPLETED)
                finally:
                    changed.cancel()
                gone = watch.done()
            if gone:
                kind, reason = watch.result()
                self.restarts += 1
                self._pool.count_loss(kind)
                code, kill = CLOSE_ERROR, kind == health.HANG
                if relay.closed_by_client:
                    code, reason = CLOSE_NORMAL, "Chrome closed by the client"
        finally:
            watch.cancel()
            await asyncio.wait([watch])
            await self._shut(code, reason, kill=kill)

    async def _shut(self, code: int, reason: str, *, kill: bool) -> None:
        """Disconnect the client, then close the Chrome (killed first when *kill*)."""
        self.state = "closing"
        relay, chrome = self.relay, self.chrome
        self.relay = self.chrome = None
        self.started = None
        try:
            if relay is not None:
                await asyncio.shield(relay.disconnect(code, reason))
        finally:
            if chrome is not None:
                if kill and chrome.alive:
                    with contextlib.suppress(ProcessLookupError):
                        os.kill(chrome.pid, signal.SIGKILL)
                try:
                    await chrome.close()
                finally:
                    if relay is not None:
                        await relay.close(code, reason)

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #

    def status(self) -> dict:
        chrome = self.chrome
        age = None if self.started is None else round(time.monotonic() - self.started, 1)
        return {
            "id": self.id,
            "state": self.state,
            "pid": chrome.pid if chrome is not None else None,
            "proxy": _public(chrome.proxy) if chrome is not None else None,
            "seed": chrome.seed if chrome is not None else None,
            "age": age,
            "launches": self.launches,
            "restarts": self.restarts,
            "launch_failures": self.failures,
            "error": self.error,
        }


def _public(proxy: str | None) -> str | None:
    """*proxy* without its credentials."""
    if not proxy:
        return None
    scheme, sep, rest = proxy.rpartition("://")
    return f"{scheme}{sep}{rest.rpartition('@')[2]}"

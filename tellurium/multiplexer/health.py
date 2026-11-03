"""Health — whether a Chrome of the pool is still alive and answering.

A probe is a ``Browser.getVersion`` on the Chrome's own pipe, through its
:class:`~tellurium.multiplexer.relay.Relay` (the reply never reaches the
client), every :data:`INTERVAL` seconds, with or without a client. A Chrome
whose pipe breaks or whose process exits has crashed; one that misses
:data:`MISSES` probes in a row (each :data:`TIMEOUT` seconds long) hangs. A
renderer crash is not the Chrome's: the client gets ``Target.targetCrashed``
and the browser process keeps answering. A probe is missed only if nothing
at all came from the pipe while it waited, and the relay was not holding the
pipe for a slow client: a Chrome that keeps talking is alive, even when the
reply sits behind what it piled up during a client's pause.

What is read counts in messages, not bytes: a message is counted once read
whole. That never hides a live Chrome: the largest one (a V8 string at its
limit, 512 MiB) comes through the pipe in under half a second (measured on
Chrome 156), far below the :data:`MISSES` x :data:`TIMEOUT` a hang takes.
"""

from __future__ import annotations

import asyncio
from typing import Any

from tellurium.multiplexer.relay import RelayClosed

#: Seconds between two probes of a Chrome that answered.
INTERVAL = 10.0
#: Seconds a probe waits for its reply.
TIMEOUT = 10.0
#: Probes missed in a row that make a Chrome hung.
MISSES = 2

CRASH = "crash"
HANG = "hang"


async def watch(relay: Any, chrome: Any) -> tuple[str, str]:
    """Probe until the Chrome is lost; returns ``(CRASH or HANG, reason)``."""
    missed = 0
    while True:
        if relay.ended.done():
            return CRASH, f"Chrome exited: {relay.ended.result()}"
        if not chrome.alive:
            return CRASH, "the Chrome process exited"
        wait = INTERVAL
        pauses, received = relay.pauses, relay.received
        try:
            await relay.probe(TIMEOUT)
            missed = 0
        except TimeoutError:
            if relay.paused or relay.pauses != pauses or relay.received != received:
                # Chrome spoke meanwhile, or the relay held the pipe for a slow
                # client: the reply is queued behind the rest, not missing.
                missed = 0
                continue
            missed += 1
            if missed >= MISSES:
                return HANG, f"Chrome did not answer {missed} health probes in a row"
            wait = 0.0  # the next probe right away
        except RelayClosed:
            continue
        if wait:
            await asyncio.wait([relay.ended], timeout=wait)

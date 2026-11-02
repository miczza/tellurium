"""Health — whether a Chrome of the pool is still alive and answering.

A probe is a ``Browser.getVersion`` on the Chrome's own pipe, through its
:class:`~tellurium.multiplexer.relay.Relay` (the reply never reaches the
client), every :data:`INTERVAL` seconds, with or without a client. A Chrome
whose pipe breaks or whose process exits has crashed; one that misses
:data:`MISSES` probes in a row (each :data:`TIMEOUT` seconds long) hangs. A
renderer crash is not the Chrome's: the client gets ``Target.targetCrashed``
and the browser process keeps answering.
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
        try:
            await relay.probe(TIMEOUT)
            missed = 0
        except TimeoutError:
            missed += 1
            if missed >= MISSES:
                return HANG, f"Chrome did not answer {missed} health probes in a row"
            wait = 0.0  # the next probe right away
        except RelayClosed:
            continue
        if wait:
            await asyncio.wait([relay.ended], timeout=wait)

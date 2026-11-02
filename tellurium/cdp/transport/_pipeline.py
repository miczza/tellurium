"""Pipelined CDP commands: issued in order, replies collected later."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("tellurium")


class CommandPipeline:
    """Session stand-in that issues commands without awaiting their replies.

    Every command reaches the transport in call order; :meth:`drain` then
    collects the replies. Only for callers that ignore command results.
    """

    def __init__(self, session: Any):
        self._session = session
        self._pending: list[asyncio.Future] = []

    async def send(self, method: str, params: dict | None = None, timeout: float | None = None):
        self._pending.append(asyncio.ensure_future(self._session.send(method, params)))
        await asyncio.sleep(0)  # let the command hit the transport before the next one
        return {}

    def on(self, event_name: str, handler: Any) -> None:
        self._session.on(event_name, handler)

    def off(self, event_name: str, handler: Any) -> None:
        self._session.off(event_name, handler)

    async def drain(self, target_id: str, timeout: float = 10) -> None:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*self._pending, return_exceptions=True), timeout=timeout
            )
        except TimeoutError:
            logger.warning("Tab %s did not acknowledge its setup commands", target_id)
            return
        for result in results:
            if isinstance(result, Exception):
                logger.debug("Setup command failed on tab %s: %r", target_id, result)

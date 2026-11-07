"""A hung async test fails instead of ending the whole pytest run.

On Windows ``pytest-timeout`` has only its thread method: at the timeout it
dumps the stacks and ends the process, so the rest of the CI shard never
runs. :func:`guarded` cancels the test a little earlier from inside its own
event loop (when the loop is waiting, which a hang on Chrome or a socket
is); a loop blocked in a call still meets ``pytest-timeout``.

``pytest-timeout`` counts the whole item, fixtures included: the guard's
clock starts when the item's setup starts (``started``), so a slow async
fixture shortens the test's share. The :data:`MARGIN` left after the guard
fires is for the teardown (closing a Chrome takes a few seconds).
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any

#: How long before ``pytest-timeout`` the guard cancels the test: the time
#: left for the teardown.
MARGIN = 15.0


def guarded(
    func: Callable[..., Awaitable[Any]],
    seconds: float,
    started: Callable[[], float | None] = lambda: None,
) -> Callable[..., Awaitable[Any]]:
    """*func* failing with ``TimeoutError`` once *seconds* have passed since
    ``started()`` (a ``time.monotonic()`` value; None: since the call), even
    if it swallows the cancellation."""

    @functools.wraps(func)
    async def run(*args: Any, **kwargs: Any) -> Any:
        begin = started()
        spent = 0.0 if begin is None else max(0.0, time.monotonic() - begin)
        limit = asyncio.timeout(max(0.0, seconds - spent))
        try:
            async with limit:
                result = await func(*args, **kwargs)
        except TimeoutError:
            if limit.expired():
                raise _expired(seconds) from None
            raise
        if limit.expired():  # the test caught the CancelledError and went on
            raise _expired(seconds)
        return result

    return run


def _expired(seconds: float) -> TimeoutError:
    return TimeoutError(
        f"still running after {seconds:g}s: cancelled before pytest-timeout ends the whole run"
    )


def guard_seconds(timeout: float | None) -> float | None:
    """The guard for a ``pytest-timeout`` of *timeout* seconds (None: none)."""
    if not timeout or timeout <= MARGIN:
        return None
    return timeout - MARGIN

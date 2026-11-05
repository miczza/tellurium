"""A hung async test fails instead of ending the whole pytest run.

On Windows ``pytest-timeout`` has only its thread method: at the timeout it
dumps the stacks and ends the process, so the rest of the CI shard never
runs. :func:`guarded` cancels the test a little earlier from inside its own
event loop (when the loop is waiting, which a hang on Chrome or a socket
is); a loop blocked in a call still meets ``pytest-timeout``.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Any

#: How long before ``pytest-timeout`` the guard cancels the test.
MARGIN = 15.0


def guarded(func: Callable[..., Awaitable[Any]], seconds: float) -> Callable[..., Awaitable[Any]]:
    """*func* failing with ``TimeoutError`` once it has run *seconds*."""

    @functools.wraps(func)
    async def run(*args: Any, **kwargs: Any) -> Any:
        limit = asyncio.timeout(seconds)
        try:
            async with limit:
                return await func(*args, **kwargs)
        except TimeoutError:
            if limit.expired():
                raise TimeoutError(
                    f"still running after {seconds:g}s: cancelled before pytest-timeout "
                    "ends the whole run"
                ) from None
            raise

    return run


def guard_seconds(timeout: float | None) -> float | None:
    """The guard for a ``pytest-timeout`` of *timeout* seconds (None: none)."""
    if not timeout or timeout <= MARGIN:
        return None
    return timeout - MARGIN

"""A test's side task, like the "person" who signs in while the test waits.

When the test fails because the side task did not do its part, the reason is
in the side task: its exception, or the await it was still stuck on. A bare
``task.cancel()`` in a ``finally`` throws both away. :func:`side_task` adds
them as a note to the test's failure, with the time the side task took, and
fails the test if the side task fails after a body that never awaited it.
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from tests.await_chain import awaiting

#: How long a cancelled side task gets to unwind before it is reported as stuck.
UNWIND = 5.0


@asynccontextmanager
async def side_task(coro: Coroutine[Any, Any, Any]) -> AsyncIterator[asyncio.Task]:
    """Run *coro* as a task for the body of the ``async with``; on the way out
    it is cancelled if still running and awaited."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    ended: list[float] = []
    task = asyncio.create_task(coro)
    task.add_done_callback(lambda _: ended.append(loop.time()))
    try:
        yield task
    except BaseException as exc:
        note = await _report(task, started, ended, loop)
        if note is not None and _failure(task) is not exc:
            exc.add_note(note)
        raise
    await _report(task, started, ended, loop)
    failure = _failure(task)
    if failure is not None:
        raise failure


async def _report(
    task: asyncio.Task, started: float, ended: list[float], loop: asyncio.AbstractEventLoop
) -> str | None:
    """What the side task did, once it is over; ``None`` if it ended well."""
    if not task.done():
        where = "\n".join(awaiting(task.get_coro()))
        took = loop.time() - started
        task.cancel()
        await asyncio.wait({task}, timeout=UNWIND)
        return f"side task still running after {took:.1f} s, at:\n{where}"
    failure = _failure(task)
    if failure is None:
        return None
    took = ended[0] - started if ended else loop.time() - started
    lines = "".join(traceback.format_exception(failure))
    return f"side task failed after {took:.1f} s:\n{lines}"


def _failure(task: asyncio.Task) -> BaseException | None:
    if not task.done() or task.cancelled():
        return None
    return task.exception()

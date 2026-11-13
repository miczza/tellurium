"""Where a coroutine is suspended: its chain of awaits, outermost first.

``Task.get_stack()`` gives only the outermost frame of a suspended task: the
awaits below it are linked through ``cr_await``, not ``f_back``. This walks
them, down to the future the innermost coroutine waits on.
"""

from __future__ import annotations

import asyncio
import gc
import inspect
import os
from typing import Any


def awaiting(coro: Any) -> list[str]:
    """The chain of awaits *coro* is suspended in, outermost first; the last
    line names the future it ends on, when it ends on one."""
    lines = []
    while coro is not None:
        coro = _generator_of(coro)
        frame = (
            getattr(coro, "cr_frame", None)
            or getattr(coro, "gi_frame", None)
            or getattr(coro, "ag_frame", None)
        )
        if frame is None:
            lines.append(f"  on {_future(coro)}")
            break
        lines.append(
            f"  {_short(frame.f_code.co_filename)}:{frame.f_lineno} in {frame.f_code.co_name}"
        )
        coro = (
            getattr(coro, "cr_await", None)
            or getattr(coro, "gi_yieldfrom", None)
            or getattr(coro, "ag_await", None)
        )
    return lines


def _generator_of(awaited: Any) -> Any:
    """The async generator behind an ``__anext__()``/``asend()`` awaitable (how
    pytest-asyncio sets up a fixture), which has no attribute for it."""
    if type(awaited).__name__ not in ("async_generator_asend", "async_generator_athrow"):
        return awaited
    return next((r for r in gc.get_referents(awaited) if inspect.isasyncgen(r)), awaited)


def tasks_report() -> str:
    """Every task of the running loop but the caller's, each with its chain of awaits."""
    current = asyncio.current_task()
    tasks = [t for t in asyncio.all_tasks() if t is not current]
    out = [f"{len(tasks)} task(s)"]
    for task in sorted(tasks, key=lambda t: t.get_name()):
        out.append(f"{task.get_name()} ({_coro_name(task.get_coro())}):")
        out.extend(awaiting(task.get_coro()) or ["  (not started, or running)"])
    return "\n".join(out)


def _future(awaited: Any) -> str:
    if isinstance(awaited, asyncio.Task):
        return f"task {awaited.get_name()} ({_coro_name(awaited.get_coro())})"
    return type(awaited).__name__  # a C future's FutureIter hides the future itself


def _coro_name(coro: Any) -> str:
    return getattr(coro, "__qualname__", None) or type(coro).__name__


def _short(filename: str) -> str:
    """Relative to the working directory when under it, else its last three parts."""
    try:
        relative = os.path.relpath(filename)
    except ValueError:  # Windows: another drive
        relative = ".."
    if not relative.startswith(".."):
        return relative
    return os.path.join("...", *filename.replace("\\", "/").split("/")[-3:])

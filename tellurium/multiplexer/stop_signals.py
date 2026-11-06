"""The signals that stop a server cleanly, caught on every system.

Ctrl-C (SIGINT), kill (SIGTERM), the terminal or ssh going away (SIGHUP, not
on Windows) and, on Windows, Ctrl-Break (SIGBREAK: what a console sends a
process group of its own, and the way to ask another process to stop there,
where SIGTERM is ``TerminateProcess``). Used by ``tellurium multiplex`` and
``tellurium mcp``.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable, Iterable
from typing import Any

#: Every stop signal, of which each system has some.
STOP_NAMES = ("SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK")


def stop_signals(names: Iterable[str] = STOP_NAMES) -> tuple[int, ...]:
    """The signals of *names* this platform has."""
    return tuple(getattr(signal, name) for name in names if hasattr(signal, name))


def catch(
    loop: asyncio.AbstractEventLoop, stop: Callable[[], Any], names: Iterable[str] = STOP_NAMES
) -> Callable[[], None]:
    """Call *stop* on each signal of *names*, until the returned function is
    called; after that those signals are ignored (blocked where the platform
    can), not back to their defaults: one that comes while the process exits
    cannot kill it nor turn its 0 into -2. Without ``loop.add_signal_handler``
    (Windows) the handlers are plain ``signal.signal`` ones that hand *stop*
    to the loop (asyncio's proactor wakes up for them)."""
    signals = stop_signals(names)
    native: list[int] = []
    try:
        for signum in signals:
            loop.add_signal_handler(signum, stop)
            native.append(signum)
    except (NotImplementedError, AttributeError):
        for signum in native:
            loop.remove_signal_handler(signum)
        native = []

        def handler(*_: Any) -> None:
            loop.call_soon_threadsafe(stop)

        for signum in signals:
            signal.signal(signum, handler)

    def release() -> None:
        if hasattr(signal, "pthread_sigmask"):
            signal.pthread_sigmask(signal.SIG_BLOCK, signals)
            for signum in native:
                loop.remove_signal_handler(signum)
            return
        for signum in native:
            loop.remove_signal_handler(signum)
        for signum in signals:
            signal.signal(signum, signal.SIG_IGN)

    return release

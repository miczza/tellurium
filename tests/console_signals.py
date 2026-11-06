"""Stopping a server under test as a person or a service manager does, on
every system.

On Windows ``send_signal(SIGTERM)`` is ``TerminateProcess`` (exit code 1, no
cleanup) and Ctrl-C cannot be sent to one process: the server is started in a
console process group of its own (:data:`NEW_GROUP`) and gets Ctrl-Break
(``CTRL_BREAK_EVENT``, ``SIGBREAK`` in Python), which it takes as Ctrl-C.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Any

WINDOWS = sys.platform == "win32"

#: Keyword arguments for ``subprocess.Popen``/``asyncio.create_subprocess_exec``
#: of a server that :func:`interrupt` and :func:`terminate` stop.
NEW_GROUP: dict[str, Any] = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {}
)


def interrupt(proc: Any) -> None:
    """Ctrl-C (SIGINT); Ctrl-Break to its group on Windows."""
    _send(proc, signal.SIGINT)


def terminate(proc: Any) -> None:
    """SIGTERM; Ctrl-Break to its group on Windows."""
    _send(proc, signal.SIGTERM)


def _send(proc: Any, signum: int) -> None:
    if WINDOWS:
        os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
    else:
        proc.send_signal(signum)

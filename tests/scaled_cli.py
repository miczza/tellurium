"""The ``tellurium`` command in a child process, with the test's navigation deadlines.

A command the tests start (``tellurium mcp``) runs in a process of its own,
where ``tests.timeout_scale`` does not reach: its navigations would wait the
library's defaults even on the slow runners. :func:`command` starts it as
``python scaled_cli.py DEADLINES ARGS...`` instead: each deadline of
:data:`CARRIED` is set first to its value in the test's own process
(stretched on the slow runners, or patched by the test), then the command runs
as ``tellurium ARGS...``. Only the navigation's deadlines are carried, the
ones a stalled runner overran in the MCP server: the others of
``timeout_scale.SCALED`` (Chrome's close grace, the cookie calls...) stay the
command's own, so a test bounding how long the server takes to stop measures
the command users get. The library and its defaults are those users get; the
child imports nothing from ``tests``.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from typing import Any

from tellurium.browser import navigation

#: Owner and attribute of each deadline the child gets from the test's process.
CARRIED: tuple[tuple[Any, str], ...] = (
    (navigation, "NAVIGATION_TIMEOUT"),
    (navigation, "LIFECYCLE_TIMEOUT"),
)


def command(*args: str) -> list[str]:
    """The argv of ``tellurium *args`` with the navigation deadlines of this process."""
    deadlines = [_deadline(owner, name) for owner, name in CARRIED]
    return [sys.executable, os.path.abspath(__file__), json.dumps(deadlines), *args]


def _deadline(owner: Any, name: str) -> list[Any]:
    """``[module, class or "", attribute, value]`` of the deadline *owner.name*."""
    if isinstance(owner, type):
        return [owner.__module__, owner.__qualname__, name, getattr(owner, name)]
    return [owner.__name__, "", name, getattr(owner, name)]


def main(argv: list[str]) -> Any:
    deadlines, *args = argv
    for module, owner, name, value in json.loads(deadlines):
        target: Any = importlib.import_module(module)
        for part in filter(None, owner.split(".")):
            target = getattr(target, part)
        setattr(target, name, value)
    from tellurium.cli import main as tellurium

    sys.argv = ["tellurium", *args]
    return tellurium()


if __name__ == "__main__":
    # Not the modules of this folder: the child is the library and the command alone.
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.curdir) != here]
    sys.exit(main(sys.argv[1:]))

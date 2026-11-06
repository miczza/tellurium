"""Chrome under test opens its windows on a private Xvfb, never on the desktop.

A headed Chrome on the user's display steals the focus at every launch, and
with ``WAYLAND_DISPLAY`` set Chrome picks Wayland even when ``DISPLAY`` names
an Xvfb. So the session starts its own Xvfb before collection (tests read
``DISPLAY`` to skip) and hides Wayland from every Chrome it launches.
``TELLURIUM_TEST_DISPLAY=host`` keeps the user's display, to watch a test.

On Windows, with ``--timeout``, async tests are guarded (``tests/async_guard.py``):
a hung one fails instead of ending the run.
"""

from __future__ import annotations

import inspect
import os
import shutil
import subprocess
import sys

from tests.async_guard import guard_seconds, guarded

_xvfb: subprocess.Popen | None = None


def pytest_configure(config) -> None:
    global _xvfb
    if os.environ.get("TELLURIUM_TEST_DISPLAY") == "host" or not shutil.which("Xvfb"):
        return
    read, write = os.pipe()
    try:
        _xvfb = subprocess.Popen(
            ["Xvfb", "-displayfd", str(write), "-screen", "0", "1920x1080x24", "-nolisten", "tcp"],
            pass_fds=(write,),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.close(write)
        write = -1
        with os.fdopen(read, closefd=True) as pipe:
            read = -1
            number = pipe.readline().strip()  # Xvfb writes it once it accepts clients
    finally:
        for fd in (read, write):
            if fd >= 0:
                os.close(fd)
    if not number.isdigit():
        pytest_unconfigure(config)
        return
    os.environ["DISPLAY"] = f":{number}"
    os.environ.pop("WAYLAND_DISPLAY", None)
    os.environ["XDG_SESSION_TYPE"] = "x11"


def pytest_unconfigure(config) -> None:
    global _xvfb
    if _xvfb is None:
        return
    _xvfb.terminate()
    try:
        _xvfb.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _xvfb.kill()
        _xvfb.wait()
    _xvfb = None


def pytest_collection_modifyitems(config, items) -> None:
    if sys.platform != "win32":
        return  # elsewhere pytest-timeout fails just the test (signal method)
    seconds = guard_seconds(getattr(config.option, "timeout", None))
    if seconds is None:
        return
    for item in items:
        if inspect.iscoroutinefunction(getattr(item, "obj", None)):
            item.obj = guarded(item.obj, seconds)

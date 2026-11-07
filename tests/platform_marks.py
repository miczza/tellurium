"""Skip marks for what a system does not have, each with a reason that names it.

Only for tests that exercise something missing on the system (``/proc``,
POSIX signals and process groups, a ``#!/bin/sh`` script as an executable,
an X display). A test that fails because of a defect in ``tellurium/`` is not
skipped here.

``HAS_DISPLAY`` is read at import time: ``tests/conftest.py`` sets ``DISPLAY``
to its private Xvfb in ``pytest_configure``, before collection.
"""

from __future__ import annotations

import os
import sys

import pytest

LINUX = sys.platform.startswith("linux")
WINDOWS = sys.platform == "win32"

#: Windows and macOS always have a desktop; elsewhere an X server is named by DISPLAY.
HAS_DISPLAY = sys.platform in ("win32", "darwin") or bool(os.environ.get("DISPLAY"))

needs_display = pytest.mark.skipif(not HAS_DISPLAY, reason="needs a display (xvfb-run)")
needs_proc = pytest.mark.skipif(not LINUX, reason="reads /proc to observe processes")
needs_posix_signals = pytest.mark.skipif(
    WINDOWS, reason="SIGKILL, SIGSTOP, SIGHUP and process groups do not exist on Windows"
)
needs_sh = pytest.mark.skipif(WINDOWS, reason="a #!/bin/sh script is not an executable on Windows")
needs_singleton_symlink = pytest.mark.skipif(
    WINDOWS, reason="Chrome's SingletonLock is a symlink only on POSIX"
)
needs_tz_env = pytest.mark.skipif(
    WINDOWS, reason="Chrome on Windows takes its time zone from Windows, not from TZ"
)

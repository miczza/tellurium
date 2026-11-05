"""The ``tellurium`` console script of the interpreter running the tests.

pip puts console scripts in the interpreter's scripts directory: next to
``python`` on Linux and macOS, in ``Scripts\\`` with an ``.exe`` on Windows.
"""

from __future__ import annotations

import sys
import sysconfig
from pathlib import Path

TELLURIUM_CLI = Path(sysconfig.get_path("scripts")) / (
    "tellurium.exe" if sys.platform == "win32" else "tellurium"
)

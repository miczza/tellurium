"""A temporary directory of one test alone, short enough for Chrome.

Chrome on Linux and macOS puts its singleton socket under the temp directory
(``<TMPDIR>/.org.chromium.Chromium.XXXXXX/SingletonSocket``), and a Unix
socket path has a limit (108 bytes on Linux, 104 on macOS). The system temp
directory is used where it is short (Linux, Windows, which has no such
socket); macOS's per-user one (``/var/folders/…/T``) is too long, so there
the POSIX ``/tmp`` is.

``FAILING_EXECUTABLE`` stands for a "Chrome" that exits at once with an
error on every system: Python refuses Chrome's ``--flags`` and exits 2.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

#: Longest temp root that leaves room for the folders and the socket name.
_MAX_ROOT = 40


def _short_root() -> str:
    system = tempfile.gettempdir()
    if sys.platform == "win32" or len(system) <= _MAX_ROOT:
        return system
    return "/tmp"  # every POSIX system has it, and it is short


#: Read once at import, before any test points ``tempfile.tempdir`` elsewhere.
SHORT_ROOT = _short_root()

FAILING_EXECUTABLE = sys.executable


def short_mkdtemp(prefix: str = "tlr") -> Path:
    """A new directory under :data:`SHORT_ROOT`; the caller removes it."""
    return Path(tempfile.mkdtemp(prefix=prefix, dir=SHORT_ROOT))


def point_temp_at(monkeypatch, root: Path) -> None:
    """Make *root* the temp directory of this process and of what it starts."""
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    for name in ("TMPDIR", "TMP", "TEMP") if sys.platform == "win32" else ("TMPDIR",):
        monkeypatch.setenv(name, str(root))


@contextlib.contextmanager
def private_temp(monkeypatch, prefix: str = "tlr") -> Iterator[Path]:
    """A short temp directory of this test alone, made the process's temp
    directory and removed at the end."""
    root = short_mkdtemp(prefix)
    point_temp_at(monkeypatch, root)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def child_temp_env(tmpdir: str) -> dict[str, str]:
    """The environment of a child process whose temp directory is *tmpdir*."""
    names = ("TMPDIR", "TMP", "TEMP") if sys.platform == "win32" else ("TMPDIR",)
    return {**os.environ, **dict.fromkeys(names, tmpdir)}

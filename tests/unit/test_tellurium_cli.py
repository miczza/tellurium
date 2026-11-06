"""The tests that run the ``tellurium`` command find it on every system."""

from __future__ import annotations

import subprocess

from tests.tellurium_cli import TELLURIUM_CLI


def test_the_console_script_is_where_pip_put_it():
    # On Windows it is Scripts\tellurium.exe, not next to python.exe.
    assert TELLURIUM_CLI.is_file()
    done = subprocess.run([str(TELLURIUM_CLI), "--help"], capture_output=True, timeout=60)
    assert done.returncode == 0

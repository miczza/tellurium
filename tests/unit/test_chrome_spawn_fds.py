"""launch_chrome_posix lands the CDP pipe on fds 3/4 whatever fds the parent got (m5)."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

if sys.platform == "win32":
    pytest.skip("POSIX fd remapping", allow_module_level=True)

# Echoes one CDP message from fd 3 back on fd 4, like a minimal Chrome.
FAKE_CHROME = textwrap.dedent(
    """\
    import os
    os.write(4, os.read(3, 100))
    """
)

# Runs in a fresh interpreter whose fds 3+ are all closed, so the parent's
# pipe ends land on the very fds the child must remap them to.
PARENT = textwrap.dedent(
    """\
    import os, sys
    from tellurium.browser.process import launch_chrome_posix
    os.closerange(3, 256)

    proc, write_fd, read_fd = launch_chrome_posix(sys.executable, ["-c", sys.argv[1]])
    print("parent fds", write_fd, read_fd, file=sys.stderr)
    os.write(write_fd, b"ping")
    os.close(write_fd)
    reply = os.read(read_fd, 100)
    proc.wait(10)
    print(reply.decode())
    """
)


def test_pipe_reaches_chrome_when_parent_fds_are_3_and_4():
    result = subprocess.run(
        [sys.executable, "-c", PARENT, FAKE_CHROME],
        capture_output=True,
        text=True,
        timeout=30,
        close_fds=True,
    )
    assert "parent fds 4 5" in result.stderr, result.stderr
    assert result.stdout.strip() == "ping", result.stderr

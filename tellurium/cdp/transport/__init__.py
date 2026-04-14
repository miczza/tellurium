"""CDP transport implementations.

Usage:
    from tellurium.cdp.transport import create_transport
    transport = create_transport(read_fd, write_fd)
    await transport.start()  # POSIX only
"""
from __future__ import annotations
import sys
from tellurium.cdp.transport._base import CDPTransport


def create_transport(read_fd: int, write_fd: int) -> CDPTransport:
    """Create a pipe transport appropriate for the current platform."""
    if sys.platform == "win32":
        from tellurium.cdp.transport._pipe_win import PipeWindowsTransport
        return PipeWindowsTransport(read_fd, write_fd)
    else:
        from tellurium.cdp.transport._pipe_posix import PipePosixTransport
        return PipePosixTransport(read_fd, write_fd)

"""Windows pipe transport for CDP."""

from __future__ import annotations

import asyncio
import json
import os
import sys

if sys.platform != "win32":
    raise ImportError("Windows-only module")

from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.transport._framing import NullFramer


class PipeWindowsTransport(CDPTransport):
    """CDP transport over Windows pipes exposed as CRT file descriptors.

    The fds come from :func:`tellurium.browser.launcher.launch_chrome_windows`
    (``msvcrt.open_osfhandle``).  Windows has no ``connect_read_pipe`` support
    in asyncio's proactor loop for anonymous pipes, so blocking ``os.read`` /
    ``os.write`` calls are pushed to the default thread executor instead.

    :meth:`close` must run only after Chrome has exited: closing an anonymous
    pipe handle while an executor thread is blocked in ``ReadFile`` on it can
    itself block.  :class:`~tellurium.browser.process.BrowserProcess` stops
    Chrome first, which ends the pending read with EOF.

    **Untested on real Windows.**
    """

    def __init__(self, read_fd: int, write_fd: int):
        self._read_fd = read_fd
        self._write_fd = write_fd
        self._framer = NullFramer()

    async def start(self) -> None:
        """No-op: the fds are usable as-is (kept for transport parity)."""

    async def send(self, data: bytes) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_sync, data)

    def _write_sync(self, data: bytes) -> None:
        os.write(self._write_fd, data)

    async def recv(self) -> dict:
        loop = asyncio.get_running_loop()
        while True:
            message = self._framer.next_message()
            if message is not None:
                return json.loads(message)
            chunk = await loop.run_in_executor(None, self._read_sync)
            if not chunk:
                raise EOFError("Pipe closed")
            self._framer.feed(chunk)

    def _read_sync(self) -> bytes:
        return os.read(self._read_fd, 1 << 20)

    async def close(self) -> None:
        for fd in (self._read_fd, self._write_fd):
            try:
                os.close(fd)
            except OSError:
                pass

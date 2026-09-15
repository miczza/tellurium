"""Windows pipe transport for CDP."""

from __future__ import annotations

import asyncio
import json
import os
import sys

if sys.platform != "win32":
    raise ImportError("Windows-only module")

from tellurium.cdp.transport._base import CDPTransport


class PipeWindowsTransport(CDPTransport):
    """CDP transport over Windows pipes exposed as CRT file descriptors.

    The fds come from :func:`tellurium.browser.launcher.launch_chrome_windows`
    (``msvcrt.open_osfhandle``).  Windows has no ``connect_read_pipe`` support
    in asyncio's proactor loop for anonymous pipes, so blocking ``os.read`` /
    ``os.write`` calls are pushed to the default thread executor instead.

    **Untested on real Windows.**
    """

    def __init__(self, read_fd: int, write_fd: int):
        self._read_fd = read_fd
        self._write_fd = write_fd
        self._buffer = bytearray()

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
            null_pos = self._buffer.find(b"\0")
            if null_pos != -1:
                raw = bytes(self._buffer[:null_pos])
                del self._buffer[: null_pos + 1]
                return json.loads(raw)
            chunk = await loop.run_in_executor(None, self._read_sync)
            if not chunk:
                raise EOFError("Pipe closed")
            self._buffer.extend(chunk)

    def _read_sync(self) -> bytes:
        return os.read(self._read_fd, 65536)

    async def close(self) -> None:
        for fd in (self._read_fd, self._write_fd):
            try:
                os.close(fd)
            except OSError:
                pass

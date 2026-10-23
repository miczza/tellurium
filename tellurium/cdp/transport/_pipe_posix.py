"""POSIX pipe transport for CDP (Linux/macOS)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import BinaryIO

from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.transport._framing import NullFramer


class PipePosixTransport(CDPTransport):
    """CDP transport over POSIX pipes (FD-based).
    Reads from read_fd, writes to write_fd.
    Messages are null-terminated JSON (ASCIIZ mode).

    The transport owns both fds from construction on: :meth:`close` releases
    them whether or not :meth:`start` ran.
    """

    def __init__(self, read_fd: int, write_fd: int):
        self._read_fd: int | None = read_fd
        self._write_fd: int | None = write_fd
        self._read_pipe: BinaryIO | None = None
        self._write_pipe: BinaryIO | None = None
        self._reader: asyncio.StreamReader | None = None
        self._read_transport: asyncio.ReadTransport | None = None
        self._write_transport: asyncio.WriteTransport | None = None
        self._framer = NullFramer()

    async def start(self) -> None:
        """Connect the FDs to the asyncio event loop."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        self._read_pipe = os.fdopen(self._read_fd, "rb", buffering=0)
        self._read_fd = None
        self._read_transport, _ = await loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), self._read_pipe
        )
        self._reader = reader
        self._write_pipe = os.fdopen(self._write_fd, "wb", buffering=0)
        self._write_fd = None
        self._write_transport, _ = await loop.connect_write_pipe(asyncio.Protocol, self._write_pipe)

    async def send(self, data: bytes) -> None:
        if self._write_transport is None:
            raise ConnectionError("Transport not started")
        self._write_transport.write(data)

    async def recv(self) -> dict:
        if self._reader is None:
            raise ConnectionError("Transport not started")
        while True:
            message = self._framer.next_message()
            if message is not None:
                return json.loads(message)
            chunk = await self._reader.read(1 << 20)
            if not chunk:
                raise EOFError("Pipe closed")
            self._framer.feed(chunk)

    async def close(self) -> None:
        """Release both ends; pending writes are dropped (Chrome is gone or going)."""
        transports = [t for t in (self._read_transport, self._write_transport) if t is not None]
        if self._read_transport is not None:
            self._read_transport.close()
        elif self._read_pipe is not None:
            self._read_pipe.close()
        if self._write_transport is not None:
            # It closes itself when Chrome closes its end; abort() would fail then.
            if not self._write_transport.is_closing():
                self._write_transport.abort()
        elif self._write_pipe is not None:
            self._write_pipe.close()
        for fd in (self._read_fd, self._write_fd):
            if fd is not None:
                os.close(fd)
        self._read_fd = self._write_fd = None
        self._read_pipe = self._write_pipe = None
        self._read_transport = self._write_transport = None
        self._reader = None
        if transports:
            # The pipe transports close their files from a call_soon callback.
            await asyncio.sleep(0)

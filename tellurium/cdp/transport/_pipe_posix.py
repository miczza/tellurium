"""POSIX pipe transport for CDP (Linux/macOS)."""

from __future__ import annotations

import asyncio
import json
import os

from tellurium.cdp.transport._base import CDPTransport


class PipePosixTransport(CDPTransport):
    """CDP transport over POSIX pipes (FD-based).
    Reads from read_fd, writes to write_fd.
    Messages are null-terminated JSON (ASCIIZ mode).
    """

    def __init__(self, read_fd: int, write_fd: int):
        self._read_fd = read_fd
        self._write_fd = write_fd
        self._reader: asyncio.StreamReader | None = None
        self._write_transport: asyncio.WriteTransport | None = None
        self._buffer = bytearray()

    async def start(self) -> None:
        """Connect the FDs to the asyncio event loop."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        read_pipe = os.fdopen(self._read_fd, "rb", buffering=0)
        await loop.connect_read_pipe(lambda: protocol, read_pipe)
        self._reader = reader
        write_pipe = os.fdopen(self._write_fd, "wb", buffering=0)
        transport, _ = await loop.connect_write_pipe(asyncio.Protocol, write_pipe)
        self._write_transport = transport

    async def send(self, data: bytes) -> None:
        if self._write_transport is None:
            raise ConnectionError("Transport not started")
        self._write_transport.write(data)

    async def recv(self) -> dict:
        if self._reader is None:
            raise ConnectionError("Transport not started")
        while True:
            null_pos = self._buffer.find(b"\0")
            if null_pos != -1:
                raw = bytes(self._buffer[:null_pos])
                del self._buffer[: null_pos + 1]
                return json.loads(raw)
            chunk = await self._reader.read(65536)
            if not chunk:
                raise EOFError("Pipe closed")
            self._buffer.extend(chunk)

    async def close(self) -> None:
        if self._write_transport:
            self._write_transport.close()
            self._write_transport = None
        self._reader = None

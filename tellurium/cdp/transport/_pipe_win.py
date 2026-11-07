"""Windows pipe transport for CDP: blocking pipe fds served by threads of its own."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import json
import os
import threading

from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.transport._framing import NullFramer

#: One read from the pipe, and how many of them may wait for :meth:`recv`:
#: past that the read thread stops reading and Chrome's writes block, as
#: with a POSIX pipe read by asyncio (which pauses past 128 KiB).
_CHUNK = 64 * 1024
_QUEUED_CHUNKS = 4


class PipeWindowsTransport(CDPTransport):
    """CDP transport over anonymous pipes exposed as CRT file descriptors.

    The fds come from :func:`tellurium.browser.launch_windows.launch_chrome_windows`
    (``msvcrt.open_osfhandle``). asyncio's proactor loop cannot watch an
    anonymous pipe, so the reads run on a thread of this transport and the
    writes on another, one at a time and in order: never on asyncio's shared
    executor, where a read blocked for the whole life of each Chrome would
    take a worker away from ``asyncio.to_thread`` for good, and two writes
    could interleave.

    At most :data:`_QUEUED_CHUNKS` reads wait for :meth:`recv`; past them
    the read thread waits, so a consumer that falls behind (the
    multiplexer's relay holding a slow client up) holds Chrome up too, and
    memory stays bounded.

    The read thread closes the read fd once Chrome closes its end (EOF):
    closing an anonymous pipe handle while a ``ReadFile`` is pending on it
    can block. :class:`~tellurium.browser.process.BrowserProcess` stops
    Chrome before :meth:`close`, which ends the pending read. Nothing here is
    Windows-specific, so the transport works on POSIX pipe fds as well.
    """

    def __init__(self, read_fd: int, write_fd: int):
        self._read_fd: int | None = read_fd
        self._write_fd: int | None = write_fd
        self._framer = NullFramer()
        self._read_lock = threading.Lock()
        self._write_lock = threading.Lock()  # held by a write: the fd stays open under it
        self._chunks: asyncio.Queue[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._writer: concurrent.futures.ThreadPoolExecutor | None = None
        self._eof = False
        self._room = threading.Semaphore(_QUEUED_CHUNKS)  # free places in _chunks
        self._closing = False  # close() ran: read on to EOF without waiting for room

    async def start(self) -> None:
        """Start the read and write threads on the running loop."""
        if self._chunks is not None:
            return
        loop = asyncio.get_running_loop()
        self._chunks = asyncio.Queue()
        self._writer = concurrent.futures.ThreadPoolExecutor(
            1, thread_name_prefix="tellurium-cdp-write"
        )
        self._reader = threading.Thread(
            target=self._read_loop,
            args=(loop, self._chunks),
            name="tellurium-cdp-read",
            daemon=True,
        )
        self._reader.start()

    def _read_loop(self, loop: asyncio.AbstractEventLoop, chunks: asyncio.Queue[bytes]) -> None:
        try:
            while True:
                if not self._closing:
                    self._room.acquire()  # close() releases it too
                fd = self._read_fd
                try:
                    chunk = os.read(fd, _CHUNK) if fd is not None else b""
                except OSError:
                    chunk = b""
                if self._closing:  # nobody reads any more: drop it, read on to EOF
                    if not chunk:
                        return
                    continue
                try:
                    loop.call_soon_threadsafe(chunks.put_nowait, chunk)
                except RuntimeError:  # the loop is closed: nobody reads any more
                    return
                if not chunk:
                    return
        finally:
            self._release_read_fd()

    def _release_read_fd(self) -> None:
        with self._read_lock:
            fd, self._read_fd = self._read_fd, None
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)

    async def send(self, data: bytes) -> None:
        if self._writer is None:
            raise ConnectionError("Transport not started or closed")
        try:
            future = self._writer.submit(self._write_all, data)
        except RuntimeError:  # shut down by close() meanwhile
            raise ConnectionError("Transport closed") from None
        await asyncio.wrap_future(future)

    def _write_all(self, data: bytes) -> None:
        view = memoryview(data)
        with self._write_lock:
            while view:
                if self._write_fd is None:
                    raise ConnectionError("Transport closed")
                view = view[os.write(self._write_fd, view) :]

    def _release_write_fd(self) -> None:
        with self._write_lock:
            fd, self._write_fd = self._write_fd, None
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)

    async def recv(self) -> dict:
        if self._chunks is None:
            raise ConnectionError("Transport not started")
        while True:
            message = self._framer.next_message()
            if message is not None:
                return json.loads(message)
            if self._eof:
                raise EOFError("Pipe closed")
            chunk = await self._chunks.get()
            self._room.release()
            if not chunk:
                self._eof = True
                raise EOFError("Pipe closed")
            self._framer.feed(chunk)

    async def close(self) -> None:
        """Release both ends; pending writes are dropped (Chrome is gone or going).

        The write end is closed once no write is under way (a write to a
        stopped Chrome fails at once); the read end only when no read thread
        holds it, else the thread closes it at EOF.
        """
        self._closing = True
        self._room.release()  # a read thread waiting for room goes on to EOF
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.shutdown(wait=False, cancel_futures=True)
        await asyncio.to_thread(self._release_write_fd)
        if self._reader is None or not self._reader.is_alive():
            self._release_read_fd()

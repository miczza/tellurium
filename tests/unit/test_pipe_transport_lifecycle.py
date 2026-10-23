"""POSIX pipe transport: large messages stay linear, close() releases both fds."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time

import pytest

if sys.platform == "win32":
    pytest.skip("POSIX pipe tests", allow_module_level=True)

from tellurium.cdp.transport._pipe_posix import PipePosixTransport


def _fd_is_open(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


async def _recv_time(size: int) -> float:
    """Seconds spent receiving one *size*-byte message written in one go."""
    child_read, parent_write = os.pipe()
    parent_read, child_write = os.pipe()
    transport = PipePosixTransport(parent_read, parent_write)
    await transport.start()
    payload = b'{"id": 1, "result": {"data": "' + b"x" * size + b'"}}\0'

    def write() -> None:
        view = memoryview(payload)
        while view:
            view = view[os.write(child_write, view) :]

    writer = threading.Thread(target=write)
    try:
        start = time.perf_counter()
        writer.start()
        msg = await asyncio.wait_for(transport.recv(), timeout=60)
        elapsed = time.perf_counter() - start
        assert len(msg["result"]["data"]) == size
        return elapsed
    finally:
        writer.join()
        await transport.close()
        os.close(child_read)
        os.close(child_write)


async def test_large_message_cost_grows_linearly():
    """A 64 MB reply must not re-scan the buffer on every chunk (quadratic)."""
    await _recv_time(1 << 20)  # warm-up
    small = min([await _recv_time(8 << 20) for _ in range(3)])
    large = min([await _recv_time(64 << 20) for _ in range(3)])
    # Linear: ~8x. Quadratic: ~64x. 20x leaves room for noise either way.
    assert large < small * 20, f"8 MB: {small:.3f}s, 64 MB: {large:.3f}s"


async def test_close_releases_the_read_fd_too():
    child_read, parent_write = os.pipe()
    parent_read, child_write = os.pipe()
    transport = PipePosixTransport(parent_read, parent_write)
    await transport.start()

    await transport.close()

    assert not _fd_is_open(parent_write)
    assert not _fd_is_open(parent_read)
    os.close(child_read)
    os.close(child_write)


async def test_close_before_start_releases_the_raw_fds():
    child_read, parent_write = os.pipe()
    parent_read, child_write = os.pipe()
    transport = PipePosixTransport(parent_read, parent_write)

    await transport.close()

    assert not _fd_is_open(parent_write)
    assert not _fd_is_open(parent_read)
    os.close(child_read)
    os.close(child_write)


async def test_messages_split_across_reads_are_reassembled():
    child_read, parent_write = os.pipe()
    parent_read, child_write = os.pipe()
    transport = PipePosixTransport(parent_read, parent_write)
    await transport.start()
    try:
        os.write(child_write, b'{"id": 1}\0{"id"')
        assert await asyncio.wait_for(transport.recv(), 5) == {"id": 1}
        recv = asyncio.ensure_future(transport.recv())
        await asyncio.sleep(0.05)
        os.write(child_write, b": 2}\0")
        assert await asyncio.wait_for(recv, 5) == {"id": 2}
    finally:
        await transport.close()
        os.close(child_read)
        os.close(child_write)


async def test_close_after_the_peer_went_away_is_quiet():
    """Chrome exited first: the write side already closed itself."""
    child_read, parent_write = os.pipe()
    parent_read, child_write = os.pipe()
    transport = PipePosixTransport(parent_read, parent_write)
    await transport.start()
    os.close(child_read)
    os.close(child_write)
    await asyncio.sleep(0.05)

    await transport.close()

    assert not _fd_is_open(parent_write)
    assert not _fd_is_open(parent_read)

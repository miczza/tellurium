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


async def _recv_time(sizes: list[int]) -> float:
    """Seconds spent receiving messages of *sizes*, written back to back in one go."""
    child_read, parent_write = os.pipe()
    parent_read, child_write = os.pipe()
    transport = PipePosixTransport(parent_read, parent_write)
    await transport.start()
    payload = b"".join(b'{"id": 1, "result": {"data": "' + b"x" * size + b'"}}\0' for size in sizes)

    def write() -> None:
        view = memoryview(payload)
        while view:
            view = view[os.write(child_write, view) :]

    writer = threading.Thread(target=write)
    try:
        start = time.perf_counter()
        writer.start()
        for size in sizes:
            msg = await asyncio.wait_for(transport.recv(), timeout=60)
            assert len(msg["result"]["data"]) == size
        return time.perf_counter() - start
    finally:
        writer.join()
        await transport.close()
        os.close(child_read)
        os.close(child_write)


async def test_large_message_cost_grows_linearly():
    """A 64 MB reply must not re-scan the buffer on every chunk (quadratic).

    The reference is the same 64 MB as eight 8 MB replies, measured right
    next to it: the two last about as long, so a loaded machine slows both
    alike (an 8 MB reply alone, ten times shorter, often slipped between the
    bursts that hit every 64 MB one: ratios up to 16 against a linear 8 under
    load). Linear: ~1x (1.0-2.0 idle and at load 60). Quadratic: ~8x (10-12
    measured with the scan restarting at every chunk).
    """
    await _recv_time([1 << 20])  # warm-up
    reference: list[float] = []
    large: list[float] = []
    for _ in range(3):
        reference.append(await _recv_time([8 << 20] * 8))
        large.append(await _recv_time([64 << 20]))
    assert min(large) < min(reference) * 4, (
        f"8 x 8 MB: {min(reference):.3f}s, 64 MB: {min(large):.3f}s"
    )


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

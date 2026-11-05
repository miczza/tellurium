"""The Windows pipe transport, on plain pipe fds (it has nothing Windows-only).

Reads and writes run on threads of the transport, not on asyncio's shared
executor; writes keep their order; EOF is reported, again and again.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading

import pytest

from tellurium.cdp.transport._pipe_win import PipeWindowsTransport

pytestmark = pytest.mark.asyncio


def _pipes():
    """(transport, chrome_read_fd, chrome_write_fd): the two ends a fake Chrome holds."""
    chrome_read, parent_write = os.pipe()
    parent_read, chrome_write = os.pipe()
    return PipeWindowsTransport(parent_read, parent_write), chrome_read, chrome_write


def _read_messages(fd: int, count: int) -> list[dict]:
    buffer = b""
    while buffer.count(b"\0") < count:
        chunk = os.read(fd, 1 << 16)
        if not chunk:
            break
        buffer += chunk
    return [json.loads(m) for m in buffer.split(b"\0")[:count]]


async def test_messages_go_both_ways():
    transport, chrome_read, chrome_write = _pipes()
    await transport.start()
    try:
        await transport.send(json.dumps({"id": 1, "method": "Browser.getVersion"}).encode() + b"\0")
        assert await asyncio.to_thread(_read_messages, chrome_read, 1) == [
            {"id": 1, "method": "Browser.getVersion"}
        ]
        # Two messages in one chunk, then one split across chunks.
        os.write(chrome_write, b'{"id": 1}\0{"id": 2}\0{"id"')
        assert await asyncio.wait_for(transport.recv(), 5) == {"id": 1}
        assert await asyncio.wait_for(transport.recv(), 5) == {"id": 2}
        os.write(chrome_write, b": 3}\0")
        assert await asyncio.wait_for(transport.recv(), 5) == {"id": 3}
    finally:
        os.close(chrome_write)
        await transport.close()
        os.close(chrome_read)


async def test_concurrent_large_writes_never_interleave():
    """Larger than a pipe's buffer, sent at once: each arrives whole and in order."""
    transport, chrome_read, chrome_write = _pipes()
    await transport.start()
    big = "x" * (300 * 1024)
    try:
        reading = asyncio.ensure_future(asyncio.to_thread(_read_messages, chrome_read, 8))
        await asyncio.gather(
            *(transport.send(json.dumps({"id": i, "pad": big}).encode() + b"\0") for i in range(8))
        )
        messages = await asyncio.wait_for(reading, 30)
        assert [m["id"] for m in messages] == list(range(8))
        assert all(m["pad"] == big for m in messages)
    finally:
        os.close(chrome_write)
        await transport.close()
        os.close(chrome_read)


async def test_reads_do_not_hold_the_shared_executor():
    """Many transports blocked on reads; asyncio.to_thread still runs at once."""
    workers = min(32, (os.cpu_count() or 1) + 4)  # asyncio's default executor
    opened = [_pipes() for _ in range(workers + 2)]
    try:
        for transport, *_ in opened:
            await transport.start()
        assert await asyncio.wait_for(asyncio.to_thread(lambda: "free"), 5) == "free"
    finally:
        for transport, chrome_read, chrome_write in opened:
            os.close(chrome_write)
            await transport.close()
            os.close(chrome_read)


async def test_eof_is_reported_on_every_recv_and_the_read_end_is_released():
    transport, chrome_read, chrome_write = _pipes()
    await transport.start()
    os.write(chrome_write, b'{"id": 7}\0')
    os.close(chrome_write)
    assert await asyncio.wait_for(transport.recv(), 5) == {"id": 7}
    for _ in range(2):
        with pytest.raises(EOFError):
            await asyncio.wait_for(transport.recv(), 5)
    transport._reader.join(5)
    assert transport._read_fd is None  # closed by the read thread at EOF
    await transport.close()
    os.close(chrome_read)


async def test_close_returns_while_chrome_still_holds_its_end():
    """The read end is left to the read thread, which closes it at EOF."""
    transport, chrome_read, chrome_write = _pipes()
    await transport.start()
    await asyncio.wait_for(transport.close(), 5)
    with pytest.raises(ConnectionError):
        await transport.send(b"{}\0")
    os.close(chrome_write)  # Chrome exits
    transport._reader.join(5)
    assert not transport._reader.is_alive() and transport._read_fd is None
    os.close(chrome_read)


async def test_close_before_start_releases_both_fds():
    transport, chrome_read, chrome_write = _pipes()
    read_fd, write_fd = transport._read_fd, transport._write_fd
    await transport.close()
    for fd in (read_fd, write_fd):
        with pytest.raises(OSError):
            os.fstat(fd)
    os.close(chrome_read)
    os.close(chrome_write)


async def test_threads_are_named_for_the_transport():
    transport, chrome_read, chrome_write = _pipes()
    await transport.start()
    try:
        await transport.send(b"{}\0")
        names = {t.name for t in threading.enumerate()}
        assert "tellurium-cdp-read" in names
        assert any(n.startswith("tellurium-cdp-write") for n in names)
    finally:
        os.close(chrome_write)
        await transport.close()
        os.close(chrome_read)

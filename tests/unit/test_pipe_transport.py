import asyncio
import json
import os
import sys
import pytest

if sys.platform == "win32":
    pytest.skip("POSIX pipe tests", allow_module_level=True)

from tellurium.cdp.transport._pipe_posix import PipePosixTransport


@pytest.fixture
async def pipe_pair():
    child_read_fd, parent_write_fd = os.pipe()
    parent_read_fd, child_write_fd = os.pipe()
    transport = PipePosixTransport(parent_read_fd, parent_write_fd)
    await transport.start()
    yield transport, child_read_fd, child_write_fd
    await transport.close()
    for fd in (child_read_fd, child_write_fd):
        try:
            os.close(fd)
        except OSError:
            pass


async def test_send_message(pipe_pair):
    transport, child_read_fd, _ = pipe_pair
    msg = {"id": 1, "method": "Page.navigate", "params": {"url": "https://example.com"}}
    await transport.send(json.dumps(msg).encode() + b"\0")
    data = os.read(child_read_fd, 4096)
    assert data.endswith(b"\0")
    parsed = json.loads(data.rstrip(b"\0"))
    assert parsed["method"] == "Page.navigate"


async def test_recv_message(pipe_pair):
    transport, _, child_write_fd = pipe_pair
    msg = {"id": 1, "result": {"frameId": "F1"}}
    os.write(child_write_fd, json.dumps(msg).encode() + b"\0")
    result = await transport.recv()
    assert result["id"] == 1
    assert result["result"]["frameId"] == "F1"


async def test_recv_multiple_messages(pipe_pair):
    transport, _, child_write_fd = pipe_pair
    msg1 = json.dumps({"id": 1, "result": {}}).encode() + b"\0"
    msg2 = json.dumps({"id": 2, "result": {}}).encode() + b"\0"
    os.write(child_write_fd, msg1 + msg2)
    r1 = await transport.recv()
    r2 = await transport.recv()
    assert r1["id"] == 1
    assert r2["id"] == 2


async def test_recv_fragmented_message(pipe_pair):
    transport, _, child_write_fd = pipe_pair
    full = json.dumps({"id": 1, "result": {"ok": True}}).encode() + b"\0"
    mid = len(full) // 2
    os.write(child_write_fd, full[:mid])
    await asyncio.sleep(0.02)
    os.write(child_write_fd, full[mid:])
    result = await transport.recv()
    assert result["id"] == 1
    assert result["result"]["ok"] is True

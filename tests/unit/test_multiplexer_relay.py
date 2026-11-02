"""The relay on a fake pipe and a fake WebSocket: ids, probes, limits."""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("websockets")

from websockets.exceptions import ConnectionClosedOK  # noqa: E402
from websockets.frames import Close  # noqa: E402

from tellurium.multiplexer import relay as relay_module  # noqa: E402
from tellurium.multiplexer.relay import Relay, RelayClosed  # noqa: E402


class FakePipe:
    def __init__(self) -> None:
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []
        self.got = asyncio.Event()

    async def send(self, data: bytes) -> None:
        assert data.endswith(b"\0")
        self.sent.append(json.loads(data[:-1]))
        self.got.set()

    async def recv(self) -> dict:
        message = await self.incoming.get()
        if message is EOFError:
            raise EOFError("Pipe closed")
        return message


class FakeSocket:
    """Messages from the client in *inbox*; ``send`` blocks while *blocked*."""

    def __init__(self) -> None:
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.out: list[dict] = []
        self.closed: tuple[int, str] | None = None
        self.unblocked = asyncio.Event()
        self.unblocked.set()

    def __aiter__(self):
        return self

    async def __anext__(self):
        message = await self.inbox.get()
        if message is None:
            raise StopAsyncIteration
        return message

    async def send(self, text: str) -> None:
        await self.unblocked.wait()
        if self.closed:
            raise ConnectionClosedOK(Close(*self.closed), None)
        self.out.append(json.loads(text))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self.closed is None:
            self.closed = (code, reason)
        self.inbox.put_nowait(None)


async def _until(predicate, timeout: float = 2.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout)


async def test_ids_are_swapped_both_ways_and_events_pass_untouched():
    pipe, ws = FakePipe(), FakeSocket()
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    for id in (5, 5):
        ws.inbox.put_nowait(json.dumps({"id": id, "method": "A", "sessionId": "S"}))
    await _until(lambda: len(pipe.sent) == 2)
    own = [m["id"] for m in pipe.sent]
    assert len(set(own)) == 2 and pipe.sent[0]["sessionId"] == "S"
    pipe.incoming.put_nowait({"method": "E", "sessionId": "S", "params": {}})
    for i in reversed(own):
        pipe.incoming.put_nowait({"id": i, "result": {"n": i}, "sessionId": "S"})
    pipe.incoming.put_nowait({"id": 999_999, "result": {}})  # nobody's: dropped
    await _until(lambda: len(ws.out) == 3)
    assert ws.out[0] == {"method": "E", "sessionId": "S", "params": {}}
    assert [m["id"] for m in ws.out[1:]] == [5, 5]
    assert [m["result"]["n"] for m in ws.out[1:]] == list(reversed(own))
    ws.inbox.put_nowait(None)
    await serving
    await relay.close()


async def test_probe_replies_never_reach_the_client_and_late_ones_are_dropped():
    pipe, ws = FakePipe(), FakeSocket()
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    with pytest.raises(TimeoutError):
        await relay.probe(0.05)
    late = pipe.sent[-1]["id"]
    pipe.incoming.put_nowait({"id": late, "result": {"product": "late"}})
    probe = asyncio.ensure_future(relay.probe(1))
    await _until(lambda: len(pipe.sent) == 2)
    pipe.incoming.put_nowait({"id": pipe.sent[-1]["id"], "result": {"product": "Chrome/1"}})
    assert (await probe)["product"] == "Chrome/1"
    assert ws.out == []
    ws.inbox.put_nowait(None)
    await serving
    await relay.close()


async def test_a_broken_pipe_closes_the_client_with_1011_and_fails_probes():
    pipe, ws = FakePipe(), FakeSocket()
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    probe = asyncio.ensure_future(relay.probe(5))
    await _until(lambda: pipe.sent)
    pipe.incoming.put_nowait(EOFError)
    with pytest.raises(RelayClosed):
        await probe
    await asyncio.wait_for(serving, 2)
    assert ws.closed[0] == 1011 and "pipe" in ws.closed[1]
    await relay.close()


async def test_a_client_that_reads_too_slowly_is_closed_with_1008(monkeypatch):
    monkeypatch.setattr(relay_module, "MAX_QUEUED_MESSAGES", 10)
    pipe, ws = FakePipe(), FakeSocket()
    ws.unblocked.clear()  # the client reads nothing
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    await _until(lambda: relay._client is not None)  # events with no client are dropped
    for n in range(20):
        pipe.incoming.put_nowait({"method": "E", "params": {"n": n}})
    await _until(lambda: ws.closed is not None)
    assert ws.closed[0] == 1008
    ws.unblocked.set()
    await asyncio.wait_for(serving, 2)
    await relay.close()


async def test_too_many_unanswered_commands_close_with_1008(monkeypatch):
    monkeypatch.setattr(relay_module, "MAX_PENDING", 3)
    pipe, ws = FakePipe(), FakeSocket()
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    for id in range(5):
        ws.inbox.put_nowait(json.dumps({"id": id, "method": "A"}))
    await asyncio.wait_for(serving, 2)
    assert ws.closed[0] == 1008 and len(pipe.sent) == 3
    await relay.close()


async def test_browser_close_from_the_client_ends_with_1000():
    pipe, ws = FakePipe(), FakeSocket()
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    ws.inbox.put_nowait(json.dumps({"id": 1, "method": "Browser.close"}))
    await _until(lambda: pipe.sent)
    pipe.incoming.put_nowait(EOFError)
    await asyncio.wait_for(serving, 2)
    assert ws.closed[0] == 1000 and relay.closed_by_client
    await relay.close()

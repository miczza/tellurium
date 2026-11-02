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
        self._gone = asyncio.Event()

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
        self._gone.set()

    async def wait_closed(self) -> None:
        await self._gone.wait()


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


async def test_a_slow_client_holds_the_pipe_up_instead_of_being_closed(monkeypatch):
    monkeypatch.setattr(relay_module, "HIGH_WATER", 200)
    pipe, ws = FakePipe(), FakeSocket()
    ws.unblocked.clear()  # the client takes nothing for now
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    await _until(lambda: relay._client is not None)  # events with no client are dropped
    for n in range(100):
        pipe.incoming.put_nowait({"method": "E", "params": {"n": n}})
    await _until(lambda: relay.paused)
    await asyncio.sleep(0.1)
    assert pipe.incoming.qsize() > 80  # left in the pipe, not queued here
    assert relay._client.queued <= 200 + 40
    ws.unblocked.set()  # it catches up: everything arrives, in order, nothing closed
    await _until(lambda: len(ws.out) == 100)
    assert [m["params"]["n"] for m in ws.out] == list(range(100))
    assert ws.closed is None and not relay.paused and relay.pauses >= 1
    ws.inbox.put_nowait(None)
    await serving
    await relay.close()


async def test_a_client_that_takes_nothing_for_long_is_closed_with_1008(monkeypatch):
    monkeypatch.setattr(relay_module, "HIGH_WATER", 100)
    monkeypatch.setattr(relay_module, "STALL_LIMIT", 0.3)
    pipe, ws = FakePipe(), FakeSocket()
    ws.unblocked.clear()
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    await _until(lambda: relay._client is not None)
    for n in range(20):
        pipe.incoming.put_nowait({"method": "E", "params": {"n": n}})
    await _until(lambda: ws.closed is not None, 5)
    assert ws.closed[0] == 1008 and "took nothing" in ws.closed[1]
    ws.unblocked.set()
    await asyncio.wait_for(serving, 2)
    await relay.close()


async def test_commands_chrome_has_not_answered_hold_the_client_back(monkeypatch):
    monkeypatch.setattr(relay_module, "MAX_PENDING", 3)
    pipe, ws = FakePipe(), FakeSocket()
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    for id in range(5):
        ws.inbox.put_nowait(json.dumps({"id": id, "method": "A"}))
    await _until(lambda: len(pipe.sent) == 3)
    await asyncio.sleep(0.05)
    assert len(pipe.sent) == 3 and ws.closed is None
    pipe.incoming.put_nowait({"id": pipe.sent[0]["id"], "result": {}})
    await _until(lambda: len(pipe.sent) == 4)
    await ws.close(1000)  # leaving while held back ends the relay
    await asyncio.wait_for(serving, 2)
    await relay.close()


async def test_bytes_chrome_has_not_answered_hold_the_client_back(monkeypatch):
    monkeypatch.setattr(relay_module, "MAX_INFLIGHT_BYTES", 1000)
    pipe, ws = FakePipe(), FakeSocket()
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    big = "x" * 600
    for id in range(3):
        ws.inbox.put_nowait(json.dumps({"id": id, "method": "A", "params": {"p": big}}))
    await _until(lambda: len(pipe.sent) == 1)  # one alone may be larger than half
    await asyncio.sleep(0.05)
    assert len(pipe.sent) == 1
    pipe.incoming.put_nowait({"id": pipe.sent[0]["id"], "result": {}})
    await _until(lambda: len(pipe.sent) == 2)
    await ws.close(1000)
    await asyncio.wait_for(serving, 2)
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

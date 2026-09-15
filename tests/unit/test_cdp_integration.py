"""Integration test: Session + Router + generated domains working together."""

import asyncio
import json

import pytest

from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.transport._session import SessionRouter
from tellurium.cdp.types import CDPError


class MockPipeTransport(CDPTransport):
    def __init__(self):
        self._inbox: list[dict] = []
        self._outbox: list[dict] = []
        self._inbox_event = asyncio.Event()
        self._closed = False

    async def send(self, data: bytes) -> None:
        msg = json.loads(data.rstrip(b"\0"))
        self._outbox.append(msg)

    async def recv(self) -> dict:
        while not self._inbox:
            if self._closed:
                raise EOFError("Transport closed")
            self._inbox_event.clear()
            await self._inbox_event.wait()
        return self._inbox.pop(0)

    async def close(self) -> None:
        self._closed = True
        self._inbox_event.set()

    def queue(self, msg: dict) -> None:
        self._inbox.append(msg)
        self._inbox_event.set()


@pytest.fixture
def transport():
    return MockPipeTransport()


@pytest.fixture
async def router(transport):
    r = SessionRouter(transport)
    task = asyncio.create_task(r.run())
    yield r
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_full_navigation_flow(router, transport):
    """Simulate: navigate to URL, wait for load event, get title."""
    transport.queue({"id": 1, "result": {"frameId": "F1", "loaderId": "L1"}})
    result = await router.root.send("Page.navigate", {"url": "https://example.com"})
    assert result["frameId"] == "F1"

    events = []
    router.root.on("Page.loadEventFired", lambda p: events.append(p))
    transport.queue({"method": "Page.loadEventFired", "params": {"timestamp": 100.0}})
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(events) == 1

    transport.queue({"id": 2, "result": {"result": {"type": "string", "value": "Example Domain"}}})
    result = await router.root.send(
        "Runtime.evaluate", {"expression": "document.title", "returnByValue": True}
    )
    assert result["result"]["value"] == "Example Domain"


async def test_multi_session_independence(router, transport):
    """Two child sessions should not interfere.

    Attach consumes ids 1 and 2 on the shared counter, so the first child send
    gets id=3 and the second gets id=4 — ids are unique per connection, not
    per session.
    """
    transport.queue({"id": 1, "result": {"sessionId": "s1"}})
    child1 = await router.attach("target-1")
    transport.queue({"id": 2, "result": {"sessionId": "s2"}})
    child2 = await router.attach("target-2")

    transport.queue({"id": 3, "result": {"title": "Tab 1"}, "sessionId": "s1"})
    r1 = await child1.send("Page.getTitle", {})
    assert r1["title"] == "Tab 1"

    transport.queue({"id": 4, "result": {"title": "Tab 2"}, "sessionId": "s2"})
    r2 = await child2.send("Page.getTitle", {})
    assert r2["title"] == "Tab 2"

    assert transport._outbox[-2]["sessionId"] == "s1"
    assert transport._outbox[-1]["sessionId"] == "s2"
    assert transport._outbox[-2]["id"] == 3
    assert transport._outbox[-1]["id"] == 4


async def test_event_routing_to_correct_session(router, transport):
    """Events should go to the correct child session."""
    transport.queue({"id": 1, "result": {"sessionId": "s1"}})
    child1 = await router.attach("target-1")
    transport.queue({"id": 2, "result": {"sessionId": "s2"}})
    child2 = await router.attach("target-2")

    events1 = []
    events2 = []
    child1.on("Network.requestWillBeSent", lambda p: events1.append(p))
    child2.on("Network.requestWillBeSent", lambda p: events2.append(p))

    transport.queue(
        {"method": "Network.requestWillBeSent", "params": {"requestId": "r1"}, "sessionId": "s1"}
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(events1) == 1
    assert len(events2) == 0

    transport.queue(
        {"method": "Network.requestWillBeSent", "params": {"requestId": "r2"}, "sessionId": "s2"}
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(events1) == 1
    assert len(events2) == 1


async def test_error_propagation(router, transport):
    """CDP errors should become CDPError exceptions."""
    transport.queue({"id": 1, "error": {"code": -32601, "message": "Method not found"}})
    with pytest.raises(CDPError) as exc_info:
        await router.root.send("NonExistent.method", {})
    assert exc_info.value.code == -32601
    assert "Method not found" in exc_info.value.message

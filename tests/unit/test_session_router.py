"""Tests for Session and SessionRouter."""
import asyncio
import json
import pytest
from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.transport._session import Session, SessionRouter
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

    def queue_response(self, msg_id: int, result: dict, session_id: str | None = None) -> None:
        msg: dict = {"id": msg_id, "result": result}
        if session_id is not None:
            msg["sessionId"] = session_id
        self._inbox.append(msg)
        self._inbox_event.set()

    def queue_error(self, msg_id: int, message: str, code: int = -32600, session_id: str | None = None) -> None:
        msg: dict = {"id": msg_id, "error": {"message": message, "code": code}}
        if session_id is not None:
            msg["sessionId"] = session_id
        self._inbox.append(msg)
        self._inbox_event.set()

    def queue_event(self, method: str, params: dict, session_id: str | None = None) -> None:
        msg: dict = {"method": method, "params": params}
        if session_id is not None:
            msg["sessionId"] = session_id
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


# 1. test_root_session_send_receive
async def test_root_session_send_receive(transport, router):
    send_task = asyncio.create_task(router.root.send("Page.navigate", {"url": "https://example.com"}))
    await asyncio.sleep(0)  # let send_task progress and enqueue the message
    transport.queue_response(1, {"frameId": "frame-1"})
    result = await send_task
    assert result == {"frameId": "frame-1"}
    assert transport._outbox[0] == {
        "id": 1,
        "method": "Page.navigate",
        "params": {"url": "https://example.com"},
    }


# 2. test_root_session_increments_ids
async def test_root_session_increments_ids(transport, router):
    t1 = asyncio.create_task(router.root.send("Page.navigate", {"url": "https://a.com"}))
    await asyncio.sleep(0)
    t2 = asyncio.create_task(router.root.send("Page.navigate", {"url": "https://b.com"}))
    await asyncio.sleep(0)
    transport.queue_response(1, {"frameId": "f1"})
    transport.queue_response(2, {"frameId": "f2"})
    r1, r2 = await asyncio.gather(t1, t2)
    assert transport._outbox[0]["id"] == 1
    assert transport._outbox[1]["id"] == 2
    assert r1 == {"frameId": "f1"}
    assert r2 == {"frameId": "f2"}


# 3. test_session_cdp_error
async def test_session_cdp_error(transport, router):
    send_task = asyncio.create_task(router.root.send("Target.createTarget", {}))
    await asyncio.sleep(0)
    transport.queue_error(1, "Target not found", code=-32602)
    with pytest.raises(CDPError) as exc_info:
        await send_task
    assert exc_info.value.code == -32602
    assert "Target not found" in exc_info.value.message


# 4. test_event_handler
async def test_event_handler(transport, router):
    received = []

    def handler(params):
        received.append(params)

    router.root.on("Page.loadEventFired", handler)
    transport.queue_event("Page.loadEventFired", {"timestamp": 1.0})
    await asyncio.sleep(0)
    await asyncio.sleep(0)  # give the run loop time to dispatch
    assert len(received) == 1
    assert received[0] == {"timestamp": 1.0}


# 5. test_event_handler_off
async def test_event_handler_off(transport, router):
    received = []

    def handler(params):
        received.append(params)

    router.root.on("Page.loadEventFired", handler)
    router.root.off("Page.loadEventFired", handler)
    transport.queue_event("Page.loadEventFired", {"timestamp": 2.0})
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert received == []


# 6. test_attach_creates_child_session
async def test_attach_creates_child_session(transport, router):
    attach_task = asyncio.create_task(router.attach("target-abc"))
    await asyncio.sleep(0)
    transport.queue_response(1, {"sessionId": "session-xyz"})
    session = await attach_task
    assert isinstance(session, Session)
    assert session._session_id == "session-xyz"
    assert "session-xyz" in router._sessions


# 7. test_child_session_send_receive
async def test_child_session_send_receive(transport, router):
    # Set up child session
    attach_task = asyncio.create_task(router.attach("target-abc"))
    await asyncio.sleep(0)
    transport.queue_response(1, {"sessionId": "session-xyz"})
    child = await attach_task

    # Child send uses the shared router counter; root used id=1 for attach, so child gets id=2
    send_task = asyncio.create_task(child.send("Runtime.evaluate", {"expression": "1+1"}))
    await asyncio.sleep(0)
    transport.queue_response(2, {"result": {"value": 2}}, session_id="session-xyz")
    result = await send_task

    assert result == {"result": {"value": 2}}
    # Child send should include sessionId
    child_msg = transport._outbox[1]
    assert child_msg["sessionId"] == "session-xyz"
    assert child_msg["method"] == "Runtime.evaluate"


# 8. test_child_session_events
async def test_child_session_events(transport, router):
    # Attach a child session
    attach_task = asyncio.create_task(router.attach("target-abc"))
    await asyncio.sleep(0)
    transport.queue_response(1, {"sessionId": "session-xyz"})
    child = await attach_task

    root_events = []
    child_events = []

    router.root.on("Page.loadEventFired", lambda p: root_events.append(p))
    child.on("Page.loadEventFired", lambda p: child_events.append(p))

    # Queue event for child session
    transport.queue_event("Page.loadEventFired", {"timestamp": 3.0}, session_id="session-xyz")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert child_events == [{"timestamp": 3.0}]
    assert root_events == []


# 9. test_detach_removes_session
async def test_detach_removes_session(transport, router):
    attach_task = asyncio.create_task(router.attach("target-abc"))
    await asyncio.sleep(0)
    transport.queue_response(1, {"sessionId": "session-xyz"})
    child = await attach_task

    assert "session-xyz" in router._sessions

    detach_task = asyncio.create_task(router.detach(child))
    await asyncio.sleep(0)
    transport.queue_response(2, {})
    await detach_task

    assert "session-xyz" not in router._sessions


# 10. test_pipe_close_rejects_pending
async def test_pipe_close_rejects_pending(transport, router):
    send_task = asyncio.create_task(router.root.send("Page.navigate", {"url": "https://example.com"}))
    await asyncio.sleep(0)  # let send proceed, future is now pending
    await transport.close()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    with pytest.raises(ConnectionError):
        await send_task


# 11. test_session_lock_serializes
async def test_session_lock_serializes(transport, router):
    # Verify that the lock exists on the session
    assert hasattr(router.root, "_lock")
    assert isinstance(router.root._lock, asyncio.Lock)

    # Verify sequential sends both work correctly (lock doesn't deadlock)
    t1 = asyncio.create_task(router.root.send("Page.navigate", {"url": "https://a.com"}))
    await asyncio.sleep(0)
    t2 = asyncio.create_task(router.root.send("Page.navigate", {"url": "https://b.com"}))
    await asyncio.sleep(0)
    transport.queue_response(1, {"ok": True})
    transport.queue_response(2, {"ok": True})
    r1, r2 = await asyncio.gather(t1, t2)
    assert r1 == {"ok": True}
    assert r2 == {"ok": True}
    # IDs must be 1 and 2 in order
    ids = [m["id"] for m in transport._outbox]
    assert ids == [1, 2]

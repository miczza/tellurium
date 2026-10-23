"""SessionRouter must never leave a send() hanging on a dead dispatch path."""

import asyncio

import pytest

from tellurium.cdp.transport._session import SessionRouter
from tests.unit.test_session_router import MockPipeTransport


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


async def test_raising_event_handler_does_not_stop_dispatch(transport, router):
    def bad_handler(params: dict) -> None:
        raise ValueError("boom")

    router.root.on("Page.loadEventFired", bad_handler)
    transport.queue_event("Page.loadEventFired", {})

    send_task = asyncio.create_task(router.root.send("Browser.getVersion"))
    await asyncio.sleep(0)
    transport.queue_response(transport._outbox[-1]["id"], {"product": "Chrome"})

    assert await asyncio.wait_for(send_task, timeout=1) == {"product": "Chrome"}


async def test_detached_session_fails_pending_sends(transport, router):
    transport.queue_response(1, {"sessionId": "S1"})
    session = await router.attach("T1")

    send_task = asyncio.create_task(session.send("Runtime.evaluate", {"expression": "1"}))
    await asyncio.sleep(0)
    transport.queue_event("Target.detachedFromTarget", {"sessionId": "S1", "targetId": "T1"})

    with pytest.raises(ConnectionError):
        await asyncio.wait_for(send_task, timeout=1)
    assert router.get_session("S1") is router.root


async def test_send_on_detached_session_fails_fast(transport, router):
    transport.queue_response(1, {"sessionId": "S1"})
    session = await router.attach("T1")
    transport.queue_event("Target.detachedFromTarget", {"sessionId": "S1", "targetId": "T1"})
    await asyncio.sleep(0.01)

    with pytest.raises(ConnectionError):
        await asyncio.wait_for(session.send("Runtime.evaluate", {}), timeout=1)


async def test_unexpected_transport_error_fails_pending_sends(transport):
    class BrokenTransport(type(transport)):
        async def recv(self) -> dict:
            await asyncio.sleep(0.01)
            raise ValueError("malformed JSON")

    router = SessionRouter(BrokenTransport())
    run_task = asyncio.create_task(router.run())
    send_task = asyncio.create_task(router.root.send("Browser.getVersion"))

    with pytest.raises(ConnectionError):
        await asyncio.wait_for(send_task, timeout=1)
    with pytest.raises(ValueError):
        await run_task

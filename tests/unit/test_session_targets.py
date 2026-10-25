"""The router knows which target each session is attached to (A2 part C)."""

from __future__ import annotations

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


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def _attached(transport, sid: str, target: str, on: str | None = None) -> None:
    info = {"targetId": target, "type": "iframe", "url": "http://x/"}
    params = {"sessionId": sid, "targetInfo": info, "waitingForDebugger": False}
    transport.queue_event("Target.attachedToTarget", params, session_id=on)


def _detached(transport, sid: str, on: str | None = None) -> None:
    transport.queue_event("Target.detachedFromTarget", {"sessionId": sid}, session_id=on)


async def test_session_exposes_its_id_and_whether_it_is_closed(transport, router):
    session = router.register("S1")
    assert session.session_id == "S1" and router.root.session_id is None
    assert not session.closed
    _detached(transport, "S1")
    await _settle()
    assert session.closed


async def test_auto_attached_session_is_found_by_target(transport, router):
    page = router.register("P")
    _attached(transport, "S1", "FRAME", on="P")
    await _settle()
    found = router.session_for_target("FRAME")
    assert found is not None and found.session_id == "S1" and found is not page
    assert router.session_for_target("OTHER") is None
    _detached(transport, "S1", on="P")
    await _settle()
    assert router.session_for_target("FRAME") is None


async def test_the_first_session_on_a_target_wins(transport, router):
    _attached(transport, "ENGINE", "FRAME")
    _attached(transport, "MINE", "FRAME")
    await _settle()
    assert router.session_for_target("FRAME").session_id == "ENGINE"


async def test_wait_for_target_returns_when_it_attaches(transport, router):
    waiter = asyncio.create_task(router.wait_for_target("FRAME", timeout=2))
    await _settle()
    _attached(transport, "S1", "FRAME")
    assert (await waiter).session_id == "S1"
    assert await router.wait_for_target("NEVER", timeout=0.05) is None


async def test_attach_through_a_session_records_its_target(transport, router):
    page = router.register("P")
    task = asyncio.create_task(router.attach("FRAME", via=page, timeout=2))
    await _settle()
    sent = transport._outbox[-1]
    assert sent["method"] == "Target.attachToTarget" and sent["sessionId"] == "P"
    transport.queue_response(sent["id"], {"sessionId": "S9"}, session_id="P")
    session = await task
    assert session.session_id == "S9" and router.session_for_target("FRAME") is session


async def test_attach_answered_too_late_is_detached(transport, router):
    page = router.register("P")
    with pytest.raises(TimeoutError):
        await router.attach("FRAME", via=page, timeout=0.05)
    attach = next(m for m in transport._outbox if m["method"] == "Target.attachToTarget")
    transport.queue_response(attach["id"], {"sessionId": "LATE"}, session_id="P")
    await _settle()
    detach = [m for m in transport._outbox if m["method"] == "Target.detachFromTarget"]
    assert detach and detach[0]["params"] == {"sessionId": "LATE"}
    assert router.session_for_target("FRAME") is None


async def test_session_remembers_auto_attach(transport, router):
    page = router.register("P")
    assert not page.auto_attaches
    task = asyncio.create_task(
        page.send("Target.setAutoAttach", {"autoAttach": True, "flatten": True})
    )
    await _settle()
    transport.queue_response(transport._outbox[-1]["id"], {}, session_id="P")
    await task
    assert page.auto_attaches

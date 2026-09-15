"""Verify CDP message IDs are globally unique across sessions on the same transport."""

from __future__ import annotations

import asyncio

import pytest

from tellurium.cdp.transport._session import Session, SessionRouter


class _FakeTransport:
    def __init__(self):
        self.sent: list[bytes] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(data)


@pytest.mark.asyncio
async def test_two_sessions_use_non_colliding_ids():
    """Root and child session must never emit the same `id` over one transport."""
    import json

    transport = _FakeTransport()
    router = SessionRouter(transport)
    root = router.root
    child = Session(router, session_id="child-1")
    router._sessions["child-1"] = child

    # Fire-and-forget: we don't care about responses here, only ids.
    async def fire(session, method):
        task = asyncio.create_task(session.send(method, {}))
        await asyncio.sleep(0)  # let the send reach transport.send
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    await fire(root, "Browser.getVersion")
    await fire(child, "Page.enable")
    await fire(root, "Browser.getVersion")
    await fire(child, "Page.enable")

    ids = [json.loads(payload.rstrip(b"\x00"))["id"] for payload in transport.sent]
    assert len(ids) == len(set(ids)), f"Duplicate ids across sessions: {ids}"
    # All ids should be consecutive starting at 1
    assert ids == sorted(ids), f"IDs not monotonic: {ids}"


@pytest.mark.asyncio
async def test_session_removes_request_id_attribute():
    """Session should no longer carry a per-session counter after the fix."""
    transport = _FakeTransport()
    router = SessionRouter(transport)
    session = Session(router, session_id="x")
    assert not hasattr(session, "_request_id"), (
        "Session still has _request_id — per-session counter not removed"
    )

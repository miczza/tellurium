"""Architectural guarantee: Runtime.enable must never be sent.

This is the Python-layer complement of patch T0.2 (Inspector ownKeys
guard in V8). Double-layer protection: architectural (here) + native
(patched Chromium). See design doc 07 and 09.
"""

import asyncio
import json

import pytest

from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.transport._session import Session, SessionRouter


class NoopTransport(CDPTransport):
    """Transport that records sent messages but never replies."""

    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False

    async def send(self, data: bytes) -> None:
        self.sent.append(json.loads(data.rstrip(b"\0")))

    async def recv(self) -> dict:
        while not self.closed:
            await asyncio.sleep(3600)
        raise EOFError("closed")

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def transport():
    return NoopTransport()


@pytest.fixture
def router(transport):
    return SessionRouter(transport)


async def test_root_session_rejects_runtime_enable(router, transport):
    """Root session must raise RuntimeError before sending Runtime.enable."""
    with pytest.raises(RuntimeError, match="Runtime.enable is forbidden"):
        await router.root.send("Runtime.enable", {})
    assert transport.sent == [], "No message should leave the transport"


async def test_child_session_rejects_runtime_enable(router, transport):
    """Child session (not root) must also reject Runtime.enable."""
    # Bypass attach() which would require a reply; construct child directly
    child = Session(router, session_id="session-xyz")
    router._sessions["session-xyz"] = child
    with pytest.raises(RuntimeError, match="Runtime.enable is forbidden"):
        await child.send("Runtime.enable", {})
    assert transport.sent == []


async def test_non_forbidden_methods_still_work(router, transport):
    """Methods not in the forbidden list must proceed to send()."""
    task = asyncio.create_task(router.root.send("Page.navigate", {"url": "about:blank"}))
    await asyncio.sleep(0)  # let send reach transport
    assert len(transport.sent) == 1
    assert transport.sent[0]["method"] == "Page.navigate"
    task.cancel()
    with pytest.raises((asyncio.CancelledError, ConnectionError)):
        await task

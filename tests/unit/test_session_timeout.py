"""Tests for Session.send() optional timeout."""

import asyncio
import json

import pytest

from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.transport._session import SessionRouter


class SilentTransport(CDPTransport):
    """Transport that accepts sends but never produces replies."""

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
    return SilentTransport()


@pytest.fixture
def router(transport):
    return SessionRouter(transport)


async def test_send_timeout_raises_timeout_error(router):
    """Session.send(timeout=0.05) must raise asyncio.TimeoutError if no reply arrives."""
    with pytest.raises(asyncio.TimeoutError):
        await router.root.send("Page.navigate", {"url": "about:blank"}, timeout=0.05)


async def test_send_timeout_cleans_pending(router):
    """After timeout, the pending future for that message_id must be removed
    so a late reply doesn't leak memory or fire on a stale future."""
    with pytest.raises(asyncio.TimeoutError):
        await router.root.send("Page.navigate", {}, timeout=0.05)
    # Internal check: no pending futures left
    assert router.root._pending == {}


async def test_send_without_timeout_uses_the_router_default(router):
    """No reply never means waiting forever: every command has a deadline."""
    assert SessionRouter.default_timeout == 30.0
    router.default_timeout = 0.05
    with pytest.raises(asyncio.TimeoutError, match=r"Page\.navigate .*0\.05"):
        await router.root.send("Page.navigate", {})
    assert router.root._pending == {}


async def test_the_timeout_error_names_the_method(router):
    with pytest.raises(asyncio.TimeoutError, match="DOM.getDocument"):
        await router.root.send("DOM.getDocument", {}, timeout=0.05)


async def test_an_explicit_timeout_overrides_the_default(router):
    router.default_timeout = 0.05
    task = asyncio.create_task(router.root.send("Page.navigate", {}, timeout=10))
    await asyncio.sleep(0.2)
    assert not task.done()
    task.cancel()


async def test_infinite_timeout_waits_indefinitely(router):
    router.default_timeout = 0.05
    task = asyncio.create_task(router.root.send("Page.navigate", {}, timeout=float("inf")))
    await asyncio.sleep(0.2)
    assert not task.done(), "timeout=inf must wait indefinitely"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

"""A session closed by a renderer crash fails with TargetCrashedError (M3)."""

from __future__ import annotations

import asyncio

import pytest

from tellurium.cdp.transport._session import SessionRouter
from tellurium.cdp.types import TargetCrashedError


class _SilentTransport:
    """Accepts every command and never answers."""

    async def send(self, data: bytes) -> None:
        pass

    async def recv(self) -> dict:
        await asyncio.Event().wait()

    async def close(self) -> None:
        pass


async def test_crash_fails_pending_and_future_commands():
    session = SessionRouter(_SilentTransport()).register("S1")
    pending = asyncio.ensure_future(session.send("Runtime.evaluate", {"expression": "1"}))
    await asyncio.sleep(0)

    session._close("Renderer crashed", TargetCrashedError)

    with pytest.raises(TargetCrashedError, match="Renderer crashed"):
        await pending
    with pytest.raises(TargetCrashedError, match="Renderer crashed"):
        await session.send("Runtime.evaluate", {"expression": "2"})


async def test_the_first_close_reason_wins():
    session = SessionRouter(_SilentTransport()).register("S1")
    session._close("Renderer crashed", TargetCrashedError)
    session._close("Browser pipe closed")

    with pytest.raises(TargetCrashedError):
        await session.send("Page.reload")


async def test_plain_close_still_raises_connection_error():
    session = SessionRouter(_SilentTransport()).register("S1")
    session._close("Target detached")

    with pytest.raises(ConnectionError) as info:
        await session.send("Page.reload")
    assert type(info.value) is ConnectionError

"""Tests for the per-frame isolated-world helper used by human-sim DOM queries."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from tellurium.stealth._isolated import get_hsim_world


def test_get_hsim_world_creates_once_per_frame():
    """First call invokes Page.createIsolatedWorld; subsequent calls hit the cache."""
    tab = MagicMock()
    tab._hsim_worlds = {}
    tab._session = MagicMock()
    tab._session.send = AsyncMock(return_value={"executionContextId": 42})

    ctx1 = asyncio.run(get_hsim_world(tab, frame_id="FRAME_A"))
    ctx2 = asyncio.run(get_hsim_world(tab, frame_id="FRAME_A"))

    assert ctx1 == 42 and ctx2 == 42
    assert tab._session.send.await_count == 1


def test_get_hsim_world_per_frame_isolation():
    """Different frame_id → different isolated world, separate CDP call."""
    tab = MagicMock()
    tab._hsim_worlds = {}
    tab._session = MagicMock()
    tab._session.send = AsyncMock(side_effect=[
        {"executionContextId": 10},
        {"executionContextId": 20},
    ])

    ctx_a = asyncio.run(get_hsim_world(tab, frame_id="FRAME_A"))
    ctx_b = asyncio.run(get_hsim_world(tab, frame_id="FRAME_B"))

    assert ctx_a == 10
    assert ctx_b == 20
    assert tab._session.send.await_count == 2


def test_get_hsim_world_passes_expected_params():
    """createIsolatedWorld must be called with the canonical worldName and
    grantUniversalAccess=False (no page-DOM mutation capability)."""
    tab = MagicMock()
    tab._hsim_worlds = {}
    tab._session = MagicMock()
    tab._session.send = AsyncMock(return_value={"executionContextId": 7})

    asyncio.run(get_hsim_world(tab, frame_id="ROOT"))

    method, params = tab._session.send.call_args[0]
    assert method == "Page.createIsolatedWorld"
    assert params["frameId"] == "ROOT"
    assert params["worldName"] == "__tellurium_hsim__"
    assert params["grantUniversalAccess"] is False


def test_get_hsim_world_falls_back_to_main_world_on_failure():
    """If createIsolatedWorld raises (e.g. very old Chrome), return None and
    callers must fall back to the main world."""
    tab = MagicMock()
    tab._hsim_worlds = {}
    tab._session = MagicMock()
    tab._session.send = AsyncMock(side_effect=RuntimeError("CDP error -32601"))

    ctx = asyncio.run(get_hsim_world(tab, frame_id="ROOT"))
    assert ctx is None
    # Failure must not poison the cache — next call retries.
    assert "ROOT" not in tab._hsim_worlds

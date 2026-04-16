"""Tests for the per-frame isolated-world helper used by human-sim DOM queries."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from tellurium.stealth._isolated import get_hsim_world
from tellurium.cdp.transport._session import Session, SessionRouter
from tellurium.browser.tab import Tab


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


# ---------------------------------------------------------------------------
# I1: empty frame_id short-circuit
# ---------------------------------------------------------------------------

def test_get_hsim_world_empty_frame_id_returns_none():
    """Empty frame_id short-circuits without a CDP call."""
    tab = MagicMock()
    tab._hsim_worlds = {}
    tab._session = MagicMock()
    tab._session.send = AsyncMock()

    ctx = asyncio.run(get_hsim_world(tab, frame_id=""))
    assert ctx is None
    tab._session.send.assert_not_awaited()


# ---------------------------------------------------------------------------
# C1: Page.frameNavigated dispatched through real Session (not MagicMock)
# ---------------------------------------------------------------------------

def _make_session() -> Session:
    """Create a Session with a fake router (no real transport needed)."""
    router = MagicMock(spec=SessionRouter)
    router._FORBIDDEN_METHODS = frozenset()
    session = Session(router, session_id=None)
    return session


def _make_tab(session: Session) -> Tab:
    """Instantiate a real Tab using *session* (no browser transport required)."""
    browser = MagicMock()
    return Tab(session, browser, target_id="TARGET_1")


def test_frame_navigated_main_frame_updates_frame_id():
    """Dispatching Page.frameNavigated for the main frame (no parentId)
    through the real Session dispatcher must update tab._frame_id.

    This is the critical regression test for C1: the handler registered in
    Tab.__init__ must be a plain function (not async def) so the synchronous
    dispatcher actually executes it.
    """
    async def _run():
        session = _make_session()
        tab = _make_tab(session)

        assert tab._frame_id == ""  # pre-condition: starts empty

        msg = {
            "method": "Page.frameNavigated",
            "params": {"frame": {"id": "FRAME_MAIN", "url": "https://example.com"}},
        }
        await session._handle_message(msg)

        assert tab._frame_id == "FRAME_MAIN"

    asyncio.run(_run())


def test_frame_navigated_subframe_pops_hsim_worlds():
    """Dispatching Page.frameNavigated for a subframe through the real Session
    dispatcher must pop the stale isolated-world entry from tab._hsim_worlds.

    C1: verifies that the handler runs synchronously via the dispatcher.
    """
    async def _run():
        session = _make_session()
        tab = _make_tab(session)

        # Pre-populate the cache as if isolated worlds were already created.
        tab._hsim_worlds["SUB_FRAME"] = 77
        tab._hsim_worlds["OTHER_FRAME"] = 88
        tab._frame_id = "FRAME_MAIN"

        msg = {
            "method": "Page.frameNavigated",
            "params": {
                "frame": {
                    "id": "SUB_FRAME",
                    "parentId": "FRAME_MAIN",
                    "url": "https://sub.example.com",
                }
            },
        }
        await session._handle_message(msg)

        assert "SUB_FRAME" not in tab._hsim_worlds
        assert tab._hsim_worlds.get("OTHER_FRAME") == 88
        # Main frame id must be unchanged (it was a subframe event).
        assert tab._frame_id == "FRAME_MAIN"

    asyncio.run(_run())

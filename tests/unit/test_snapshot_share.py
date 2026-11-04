"""When snapshots share the AX tree request in flight: only if the tab sent nothing else
since it went out, counted on the ids the router really allocated."""

from __future__ import annotations

import asyncio

import pytest

from tellurium.browser import snapshot


class _Router:
    """Allocates the command ids, as the real router does on each send."""

    _next_msg_id = 0


class _Session:
    """A session on *router*; a closed one raises before allocating an id, as the
    real one does; ``getFullAXTree`` waits for *release*."""

    def __init__(self, router: _Router, *, closed: bool = False):
        self.router, self.closed = router, closed
        self.release = asyncio.Event()
        self.trees = 0

    async def send(self, method, params=None, timeout=None):
        if self.closed:
            raise ConnectionError("Target detached")
        self.router._next_msg_id += 1
        if method == "Accessibility.getFullAXTree":
            self.trees += 1
            await self.release.wait()
            return {"nodes": [], "tree": self.trees}
        return {}


async def _flush() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_a_failed_send_on_a_closed_session_does_not_hide_a_later_input():
    """A snapshot command on a closed session (an OOPIF gone, Accessibility.disable on
    a dead tab) allocates no id: an input after it still makes the tree in flight
    stale, and the next snapshot asks for its own."""
    router = _Router()
    tab, gone = _Session(router), _Session(router, closed=True)
    first = asyncio.ensure_future(snapshot._full_tree(tab, None, "doc", 5, {}))
    await _flush()
    assert tab.trees == 1
    with pytest.raises(ConnectionError):
        await snapshot._send(gone, "Accessibility.disable", {}, 1)
    await tab.send("Input.dispatchMouseEvent", {})  # a click, not a snapshot's
    second = asyncio.ensure_future(snapshot._full_tree(tab, None, "doc", 5, {}))
    await _flush()
    tab.release.set()
    await asyncio.gather(first, second)
    assert tab.trees == 2


async def test_snapshots_with_nothing_else_sent_still_share_the_request():
    router = _Router()
    tab = _Session(router)
    first = asyncio.ensure_future(snapshot._full_tree(tab, None, "doc", 5, {}))
    await _flush()
    second = asyncio.ensure_future(snapshot._full_tree(tab, None, "doc", 5, {}))
    await _flush()
    tab.release.set()
    await asyncio.gather(first, second)
    assert tab.trees == 1

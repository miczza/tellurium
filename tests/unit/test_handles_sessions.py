"""Handles of a cross-site iframe are released on that iframe's session (A2 part C)."""

from __future__ import annotations

import gc

from tellurium.browser.element import Element
from tellurium.browser.handles import HandleGroup


class _Session:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    async def send(self, method, params=None, timeout=None):
        self.sent.append((method, params or {}))
        return {}


class _Tab:
    def __init__(self, session) -> None:
        self._session = session
        self._handles = HandleGroup(session)


def _released(session) -> list[str]:
    return [p["objectId"] for m, p in session.sent if m == "Runtime.releaseObject"]


def _groups(session) -> list[str]:
    return [p["objectGroup"] for m, p in session.sent if m == "Runtime.releaseObjectGroup"]


async def test_element_of_an_oopif_is_released_on_its_session():
    page, oopif = _Session(), _Session()
    tab = _Tab(page)
    element = Element(oopif, tab, object_id="O1")
    await element.release()
    assert _released(oopif) == ["O1"] and _released(page) == []


async def test_dropped_oopif_element_is_released_on_its_session():
    page, oopif = _Session(), _Session()
    tab = _Tab(page)
    Element(oopif, tab, object_id="O2")
    Element(page, tab, object_id="P2")
    gc.collect()
    await tab._handles.drain()
    assert _released(oopif) == ["O2"] and _released(page) == ["P2"]


async def test_discard_on_a_given_session():
    page, oopif = _Session(), _Session()
    tab = _Tab(page)
    tab._handles.discard("O3", oopif)
    await tab._handles.drain()
    assert _released(oopif) == ["O3"] and _released(page) == []


async def test_rotate_and_close_release_the_group_on_every_session_used():
    page, oopif = _Session(), _Session()
    tab = _Tab(page)
    first = tab._handles.name
    keep = Element(oopif, tab, object_id="O4")
    tab._handles.rotate()
    await tab._handles.drain()
    assert _groups(page) == [first] and _groups(oopif) == [first]
    second = tab._handles.name
    keep2 = Element(oopif, tab, object_id="O5")
    await tab._handles.close()
    assert _groups(oopif) == [first, second] and _groups(page) == [first, second]
    del keep, keep2

"""Tab handle bookkeeping (R1: M4, m6, m9) against a scripted CDP session."""

from __future__ import annotations

import gc
from unittest.mock import AsyncMock, MagicMock

import pytest

from tellurium.browser.handles import StaleElementError, as_stale
from tellurium.browser.tab import Tab
from tellurium.cdp.types import CDPError

VANISHED = "No node with given id found"


def _tab(*, node_ids=(), vanished=()):
    """Tab whose DOM queries return *node_ids*; resolving *vanished* ids fails."""
    sent: list[tuple[str, dict]] = []
    handlers: dict[str, list] = {}

    async def _send(method, params=None, timeout=None):
        params = params or {}
        sent.append((method, params))
        if method == "DOM.getDocument":
            return {"root": {"nodeId": 1}}
        if method == "DOM.querySelectorAll":
            return {"nodeIds": list(node_ids)}
        if method == "DOM.performSearch":
            return {"searchId": "s", "resultCount": len(node_ids)}
        if method == "DOM.getSearchResults":
            return {"nodeIds": list(node_ids)}
        if method == "DOM.resolveNode":
            if params["nodeId"] in vanished:
                raise CDPError(VANISHED, -32000)
            return {"object": {"objectId": f"OBJ{params['nodeId']}"}}
        return {}

    session = MagicMock()
    session.send = AsyncMock(side_effect=_send)
    session.on = MagicMock(side_effect=lambda name, fn: handlers.setdefault(name, []).append(fn))
    browser = MagicMock()
    browser._close_tab = AsyncMock()
    tab = Tab(session, browser, "T1")
    return tab, sent, handlers


def _methods(sent, name):
    return [params for method, params in sent if method == name]


@pytest.mark.parametrize("query", ["select_all", "xpath_all"])
async def test_bulk_queries_skip_nodes_that_vanish_before_resolve(query):
    tab, _, _ = _tab(node_ids=[2, 3, 4], vanished={3})
    elements = await getattr(tab, query)("div")
    assert [e._object_id for e in elements] == ["OBJ2", "OBJ4"]


async def test_xpath_returns_none_when_the_node_vanished():
    tab, _, _ = _tab(node_ids=[3], vanished={3})
    assert await tab.xpath("//div", timeout=0) is None


async def test_nodes_resolve_into_the_tab_object_group():
    tab, sent, _ = _tab(node_ids=[2])
    await tab.select_all("div")
    assert _methods(sent, "DOM.resolveNode")[0]["objectGroup"] == tab._handles.name


async def test_dropped_elements_are_released_in_a_batch():
    tab, sent, _ = _tab(node_ids=[2, 3])
    elements = await tab.select_all("div")
    del elements
    gc.collect()
    await tab._handles.drain()
    released = {p["objectId"] for p in _methods(sent, "Runtime.releaseObject")}
    assert released == {"OBJ2", "OBJ3"}


async def test_kept_elements_are_not_released():
    tab, sent, _ = _tab(node_ids=[2])
    kept = await tab.select_all("div")
    gc.collect()
    await tab._handles.drain()
    assert _methods(sent, "Runtime.releaseObject") == []
    assert kept


async def test_main_frame_navigation_rotates_and_releases_the_old_group():
    tab, sent, handlers = _tab()
    old = tab._handles.name
    for handler in handlers["Page.frameNavigated"]:
        handler({"frame": {"id": "F", "parentId": "P", "url": "x"}})
    assert tab._handles.name == old  # iframe navigation: same group
    for handler in handlers["Page.frameNavigated"]:
        handler({"frame": {"id": "F", "url": "x"}})
    await tab._handles.drain()
    assert tab._handles.name != old
    assert _methods(sent, "Runtime.releaseObjectGroup") == [{"objectGroup": old}]


async def test_close_releases_the_group():
    tab, sent, _ = _tab()
    name = tab._handles.name
    await tab.close()
    assert {"objectGroup": name} in _methods(sent, "Runtime.releaseObjectGroup")


async def test_release_sends_release_object_once_and_marks_stale():
    tab, sent, _ = _tab(node_ids=[2])
    (element,) = await tab.select_all("div")
    await element.release()
    await element.release()
    assert _methods(sent, "Runtime.releaseObject") == [{"objectId": "OBJ2"}]
    with pytest.raises(StaleElementError):
        await element.text()


def test_destroyed_context_maps_to_stale_element_error():
    err = as_stale(CDPError("Cannot find context with specified id", -32000))
    assert isinstance(err, StaleElementError)
    assert isinstance(err, CDPError)
    other = CDPError("Something else", -32000)
    assert as_stale(other) is other


async def test_select_retries_when_the_document_is_swapped_mid_query():
    """A popup swaps about:blank for its page between getDocument and querySelector."""
    tab, sent, _ = _tab(node_ids=[2])
    calls = {"n": 0}
    original = tab._session.send.side_effect

    async def _send(method, params=None, timeout=None):
        if method == "DOM.querySelector":
            calls["n"] += 1
            if calls["n"] == 1:
                raise CDPError("Could not find node with given id", -32000)
            return {"nodeId": 2}
        return await original(method, params, timeout)

    tab._session.send.side_effect = _send
    element = await tab.select("#msg", timeout=2)
    assert element._object_id == "OBJ2"
    assert await tab.wait_for("#msg", state="attached", timeout=2) is not None


async def test_select_still_raises_on_an_invalid_selector():
    tab, _, _ = _tab()
    original = tab._session.send.side_effect

    async def _send(method, params=None, timeout=None):
        if method == "DOM.querySelector":
            raise CDPError("DOM Error while querying", -32000)
        return await original(method, params, timeout)

    tab._session.send.side_effect = _send
    with pytest.raises(CDPError, match="querying"):
        await tab.select("##", timeout=2)

"""Tab.xpath must release every DOM search result set it creates.

Without DOM.discardSearchResults each poll iteration leaked one result set
inside the browser's DOM agent for the lifetime of the tab.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tellurium.browser.tab import Tab


def _tab_with_search(sequence):
    """*sequence* is the list of resultCount values returned per poll."""
    counts = list(sequence)
    sent: list[tuple[str, dict]] = []

    async def _send(method, params=None, timeout=None):
        sent.append((method, params or {}))
        if method == "DOM.getDocument":
            return {"root": {"nodeId": 1}}
        if method == "DOM.performSearch":
            count = counts.pop(0) if counts else 0
            return {"searchId": f"s{len(sent)}", "resultCount": count}
        if method == "DOM.getSearchResults":
            return {"nodeIds": [42]}
        return {}

    session = MagicMock()
    session.send = AsyncMock(side_effect=_send)
    session.on = MagicMock()
    browser = MagicMock()
    browser._stealth_engine = None
    tab = Tab(session, browser, "T1")
    return tab, sent


@pytest.mark.asyncio
async def test_xpath_discards_search_results_on_hit():
    tab, sent = _tab_with_search([1])
    element = await tab.xpath("//div")
    assert element is not None
    methods = [m for m, _ in sent]
    assert methods.count("DOM.performSearch") == 1
    assert methods.count("DOM.discardSearchResults") == 1


@pytest.mark.asyncio
async def test_xpath_discards_search_results_on_every_miss():
    tab, sent = _tab_with_search([0, 0, 0])
    assert await tab.xpath("//div", timeout=0.25) is None
    methods = [m for m, _ in sent]
    searches = methods.count("DOM.performSearch")
    assert searches >= 1
    assert methods.count("DOM.discardSearchResults") == searches, (
        "every performSearch must be paired with a discardSearchResults"
    )


@pytest.mark.asyncio
async def test_xpath_discards_the_matching_search_id():
    tab, sent = _tab_with_search([1])
    await tab.xpath("//div")
    search_id = next(p for m, p in sent if m == "DOM.performSearch")
    performed = [p for m, p in sent if m == "DOM.getSearchResults"][0]["searchId"]
    discarded = [p for m, p in sent if m == "DOM.discardSearchResults"][0]["searchId"]
    assert discarded == performed
    assert search_id  # params sanity

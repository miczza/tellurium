"""Element API surface promised by design doc 03: text split, tree walk, relative queries."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tellurium.browser.element import Element


def _fake_element(*, call_result=None, array_items=(), node_ids=None):
    """Element whose Runtime.callFunctionOn returns a scripted remote object."""
    sent: list[tuple[str, dict]] = []
    node_ids = list(node_ids or [])

    async def _send(method, params=None, timeout=None):
        params = params or {}
        sent.append((method, params))
        if method == "DOM.resolveNode":
            return {"object": {"objectId": "SELF"}}
        if method == "Runtime.callFunctionOn":
            return {"result": call_result or {"type": "undefined"}}
        if method == "Runtime.getProperties":
            return {
                "result": [
                    {"name": str(i), "value": {"objectId": oid}}
                    for i, oid in enumerate(array_items)
                ]
                + [{"name": "length", "value": {"value": len(array_items)}}]
            }
        if method == "DOM.requestNode":
            return {"nodeId": node_ids.pop(0) if node_ids else 0}
        return {}

    session = MagicMock()
    session.send = AsyncMock(side_effect=_send)
    tab = MagicMock()
    element = Element(session, tab, 42)
    element._sent = sent
    return element


# ---------------------------------------------------------------------------
# text / own_text / text_all
# ---------------------------------------------------------------------------


async def test_text_reads_only_direct_child_text_nodes():
    element = _fake_element(call_result={"type": "string", "value": "Price"})
    assert await element.text() == "Price"
    js = dict(element._sent)["Runtime.callFunctionOn"]["functionDeclaration"]
    assert "nodeType === 3" in js
    assert "textContent" not in js
    assert ".trim()" in js


async def test_own_text_is_an_alias_of_text():
    element = _fake_element(call_result={"type": "string", "value": "Price"})
    assert await element.own_text() == "Price"


async def test_text_all_reads_the_whole_subtree():
    element = _fake_element(call_result={"type": "string", "value": "Price 9.99"})
    assert await element.text_all() == "Price 9.99"
    js = dict(element._sent)["Runtime.callFunctionOn"]["functionDeclaration"]
    assert "this.textContent" in js


async def test_text_of_an_empty_element_is_an_empty_string():
    element = _fake_element(call_result={"type": "string", "value": None})
    assert await element.text() == ""


# ---------------------------------------------------------------------------
# children / parent
# ---------------------------------------------------------------------------


async def test_children_maps_the_array_to_elements():
    element = _fake_element(
        call_result={"type": "object", "subtype": "array", "objectId": "ARR"},
        array_items=("A", "B"),
    )
    children = await element.children()
    assert [c._object_id for c in children] == ["A", "B"]
    # Refreshing the document would void the nodeIds of every other Element.
    assert "DOM.getDocument" not in [m for m, _ in element._sent]


async def test_parent_returns_an_element():
    element = _fake_element(
        call_result={"type": "object", "subtype": "node", "objectId": "P"},
    )
    parent = await element.parent()
    assert parent is not None and parent._object_id == "P"


async def test_parent_of_the_root_is_none():
    element = _fake_element(call_result={"type": "object", "subtype": "null"})
    assert await element.parent() is None


# ---------------------------------------------------------------------------
# Relative find / xpath
# ---------------------------------------------------------------------------


async def test_find_all_scopes_the_tree_walker_to_this_element():
    element = _fake_element(
        call_result={"type": "object", "subtype": "array", "objectId": "ARR"},
        array_items=("A",),
    )
    found = await element.find_all("Buy")
    assert [e._object_id for e in found] == ["A"]
    call = dict(element._sent)["Runtime.callFunctionOn"]
    assert "createTreeWalker(this" in call["functionDeclaration"]
    assert call["arguments"] == [{"value": "Buy"}, {"value": False}]


async def test_find_raises_when_nothing_matches():
    element = _fake_element(call_result={"type": "object", "subtype": "array", "objectId": "ARR"})
    with pytest.raises(LookupError):
        await element.find("Buy")


async def test_xpath_is_evaluated_with_this_element_as_context():
    element = _fake_element(
        call_result={"type": "object", "subtype": "array", "objectId": "ARR"},
        array_items=("A", "B"),
    )
    matches = await element.xpath_all(".//a")
    assert [m._object_id for m in matches] == ["A", "B"]
    call = dict(element._sent)["Runtime.callFunctionOn"]
    assert "expr, this" in call["functionDeclaration"]
    assert "ORDERED_NODE_SNAPSHOT_TYPE" in call["functionDeclaration"]
    assert call["arguments"] == [{"value": ".//a"}]


async def test_relative_xpath_returns_none_when_empty():
    element = _fake_element(call_result={"type": "object", "subtype": "array", "objectId": "ARR"})
    assert await element.xpath("./nope") is None


# ---------------------------------------------------------------------------
# type(typos=...)
# ---------------------------------------------------------------------------


async def test_type_forwards_typos_to_the_tab():
    element = _fake_element(call_result={"type": "undefined"})
    element._tab.keyboard_type = AsyncMock()
    await element.type("hello", human=True, typos=True, wpm=70)
    element._tab.keyboard_type.assert_awaited_once_with("hello", human=True, wpm=70, typos=True)


async def test_type_defaults_to_no_typos():
    element = _fake_element(call_result={"type": "undefined"})
    element._tab.keyboard_type = AsyncMock()
    await element.type("hello")
    assert element._tab.keyboard_type.await_args.kwargs["typos"] is False

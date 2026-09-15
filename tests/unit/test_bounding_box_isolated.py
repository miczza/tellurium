"""Test Element.bounding_box_isolated() runs in the __tellurium_hsim__ world."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from tellurium.browser.element import Element


def _make_element(tab, selector="#target", frame_id="MAIN_FRAME"):
    """Construct a minimal Element without going through Tab.select()."""
    el = Element.__new__(Element)
    el._tab = tab
    el._session = tab._session
    el._node_id = 123
    el._object_id = "OBJ_123"
    el._frame_id = frame_id
    el._selector = selector
    return el


def test_bounding_box_isolated_uses_hsim_context():
    """Runtime.evaluate must be called with contextId = hsim world id, not main.

    I3: assertion is hardened to filter by method name so adding preliminary
    CDP calls does not break the index.
    """
    tab = MagicMock()
    tab._hsim_worlds = {}
    tab._session = MagicMock()
    # Mock Page.createIsolatedWorld then Runtime.evaluate
    tab._session.send = AsyncMock(
        side_effect=[
            {"executionContextId": 99},  # createIsolatedWorld
            {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 40}}},  # evaluate
        ]
    )
    tab._frame_id = "MAIN_FRAME"

    el = _make_element(tab)

    box = asyncio.run(el.bounding_box_isolated())
    assert box == {"x": 10, "y": 20, "width": 100, "height": 40}

    # I3: filter by method name rather than brittle positional index.
    evaluate_calls = [c for c in tab._session.send.call_args_list if c[0][0] == "Runtime.evaluate"]
    assert len(evaluate_calls) == 1
    method, params = evaluate_calls[0][0]
    assert params["contextId"] == 99
    assert params["returnByValue"] is True


# ---------------------------------------------------------------------------
# C2: Runtime.evaluate returning null falls back to bounding_box()
# ---------------------------------------------------------------------------


def test_bounding_box_isolated_null_result_falls_back():
    """When Runtime.evaluate returns null (selector no longer matches), the
    method must fall back to bounding_box() instead of raising TypeError."""
    tab = MagicMock()
    tab._hsim_worlds = {}
    tab._session = MagicMock()
    # Side effects:
    #   1. Page.createIsolatedWorld → gives context 55
    #   2. Runtime.evaluate → returns {"result": {"value": None}} (selector miss)
    #   3. Runtime.callFunctionOn (from bounding_box fallback) → returns rect
    tab._session.send = AsyncMock(
        side_effect=[
            {"executionContextId": 55},  # createIsolatedWorld
            {"result": {"value": None}},  # evaluate returns null
            {
                "result": {
                    "type": "object",
                    "value": {"x": 5, "y": 15, "width": 200, "height": 50},
                }
            },  # callFunctionOn for bounding_box() fallback
        ]
    )
    tab._frame_id = "MAIN_FRAME"

    el = _make_element(tab)

    box = asyncio.run(el.bounding_box_isolated())
    # Must return the fallback rect, not raise.
    assert box == {"x": 5, "y": 15, "width": 200, "height": 50}

    # Runtime.evaluate was called (attempted isolated world first).
    evaluate_calls = [c for c in tab._session.send.call_args_list if c[0][0] == "Runtime.evaluate"]
    assert len(evaluate_calls) == 1

    # The fallback bounding_box() path used Runtime.callFunctionOn.
    cfo_calls = [c for c in tab._session.send.call_args_list if c[0][0] == "Runtime.callFunctionOn"]
    assert len(cfo_calls) == 1

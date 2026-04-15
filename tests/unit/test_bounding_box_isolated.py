"""Test Element.bounding_box_isolated() runs in the __tellurium_hsim__ world."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from tellurium.browser.element import Element


def test_bounding_box_isolated_uses_hsim_context():
    """Runtime.evaluate must be called with contextId = hsim world id, not main."""
    tab = MagicMock()
    tab._hsim_worlds = {}
    tab._session = MagicMock()
    # Mock Page.createIsolatedWorld then Runtime.evaluate
    tab._session.send = AsyncMock(side_effect=[
        {"executionContextId": 99},  # createIsolatedWorld
        {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 40}}},  # evaluate
    ])
    tab._frame_id = "MAIN_FRAME"

    el = Element.__new__(Element)
    el._tab = tab
    el._session = tab._session
    el._node_id = 123
    el._object_id = "OBJ_123"
    el._frame_id = "MAIN_FRAME"
    el._selector = "#target"

    box = asyncio.run(el.bounding_box_isolated())
    assert box == {"x": 10, "y": 20, "width": 100, "height": 40}

    evaluate_call = tab._session.send.call_args_list[1]
    method, params = evaluate_call[0]
    assert method == "Runtime.evaluate"
    assert params["contextId"] == 99
    assert params["returnByValue"] is True

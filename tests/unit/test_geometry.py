"""Element boxes from DOM.getContentQuads (``tellurium.browser.geometry``)."""

from __future__ import annotations

import pytest

from tellurium.browser import geometry
from tellurium.browser.handles import StaleElementError


class _Session:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    async def send(self, method, params=None, timeout=None):
        self.calls.append((method, params))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


class _Tab:
    def __init__(self):
        self.events = []

    async def _human_action(self, action):
        pass

    async def mouse_move(self, x, y, human=False):
        self.events.append(("move", x, y))

    async def _dispatch_mouse(self, params):
        self.events.append((params["type"], params["x"], params["y"]))


class _Element:
    def __init__(self, session):
        self._session = session
        self._tab = _Tab()

    async def _resolve(self):
        return "obj-1"

    async def scroll_into_view(self, human=False):
        pass


def _quads(x, y, w, h):
    return {"quads": [[x, y, x + w, y, x + w, y + h, x, y + h]]}


async def test_content_box_is_the_largest_fragment_in_page_coordinates():
    session = _Session(
        {"quads": [[0, 0, 10, 0, 10, 5, 0, 5], [400, 300, 480, 300, 480, 330, 400, 330]]}
    )
    box = await geometry.content_box(_Element(session))
    assert box == {"x": 400, "y": 300, "width": 80, "height": 30}
    assert session.calls == [("DOM.getContentQuads", {"objectId": "obj-1"})]


@pytest.mark.parametrize("answer", [{"quads": []}, {}, _quads(10, 10, 0, 20)])
async def test_no_box_or_an_empty_box_is_stale(answer):
    with pytest.raises(StaleElementError):
        await geometry.content_box(_Element(_Session(answer)))


def test_center_stays_inside_even_a_tiny_box():
    box = {"x": 5, "y": 5, "width": 2, "height": 2}
    for _ in range(200):
        assert geometry.contains(box, *geometry.center(box, jitter=3))


async def test_human_click_presses_where_the_box_still_is():
    element = _Element(_Session(_quads(400, 300, 80, 30)))
    await geometry.human_click(element)
    kinds = [event[0] for event in element._tab.events]
    assert kinds == ["move", "mousePressed", "mouseReleased"]
    _, x, y = element._tab.events[1]
    assert 400 <= x <= 480 and 300 <= y <= 330


@pytest.mark.parametrize("after", [{"quads": []}, _quads(0, 0, 40, 40)])
async def test_human_click_sends_no_press_if_the_node_went_or_moved(after):
    element = _Element(_Session(_quads(400, 300, 80, 30), after))
    with pytest.raises(StaleElementError):
        await geometry.human_click(element)
    assert [event[0] for event in element._tab.events] == ["move"]

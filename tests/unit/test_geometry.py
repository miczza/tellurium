"""Element boxes from DOM.getContentQuads (``tellurium.browser.geometry``)."""

from __future__ import annotations

import pytest

from tellurium.browser import geometry
from tellurium.browser.handles import StaleElementError


class _Session:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    hit = 7  # backend id getNodeForLocation answers; the element is 7

    async def send(self, method, params=None, timeout=None):
        self.calls.append((method, params))
        if method == "DOM.getNodeForLocation":
            return {"backendNodeId": self.hit, "frameId": "main"}
        if method == "DOM.describeNode":
            node = params.get("backendNodeId", 7)
            return {
                "node": {"backendNodeId": node, "localName": "div", "attributes": ["id", "cover"]}
            }
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "main"}}}
        if method == "DOM.resolveNode":
            return {"object": {"objectId": f"o{params['backendNodeId']}"}}
        if method == "Runtime.callFunctionOn":
            return {"result": {"value": False}}
        if method == "Runtime.releaseObject":
            return {}
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
    # no frame in the page: no zoom to undo, nothing asked past the frame tree
    assert session.calls == [
        ("DOM.getContentQuads", {"objectId": "obj-1"}),
        ("Page.getFrameTree", {}),
    ]


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


async def test_human_click_sends_nothing_when_another_node_is_on_top():
    session = _Session(_quads(400, 300, 80, 30))
    session.hit = 99
    element = _Element(session)
    with pytest.raises(geometry.ElementNotHittableError, match='<div id="cover"> is on top'):
        await geometry.human_click(element)
    assert [event[0] for event in element._tab.events] == ["move"]


def test_frame_chain_climbs_from_an_oopif_to_the_tab():
    class Session:
        pass

    tab, outer, inner = Session(), Session(), Session()
    geometry.link_frame(outer, tab, "F1")
    geometry.link_frame(inner, outer, "F2")
    assert geometry.frame_chain(inner) == [(inner, outer, "F2"), (outer, tab, "F1")]
    assert geometry.frame_chain(tab) == []


# A rectangle 400x300 seen in perspective: its right side is farther, so shorter.
_TILTED = [(100.0, 50.0), (420.0, 90.0), (420.0, 290.0), (100.0, 350.0)]


def test_a_frame_map_takes_the_corners_of_the_frame_to_its_quad():
    homography = geometry._Homography.of_rect(400, 300, _TILTED)
    for (u, v), point in zip([(0, 0), (400, 0), (400, 300), (0, 300)], _TILTED, strict=True):
        assert homography.apply(u, v) == pytest.approx(point)


def test_a_frame_map_in_perspective_is_not_affine_and_inverts():
    homography = geometry._Homography.of_rect(400, 300, _TILTED)
    # the centre of the frame is not the average of the corners in perspective: it is
    # nearer the far (short) side
    x, y = homography.apply(200, 150)
    assert x > 260 + 1
    for u, v in [(10, 10), (200, 150), (390, 20), (35.5, 280.25)]:
        assert homography.invert(*homography.apply(u, v)) == pytest.approx((u, v))
    moved = homography.then_after(10, 20)
    assert moved.apply(5, 5) == pytest.approx(homography.apply(15, 25))


def test_a_flat_rectangle_maps_like_an_affine_one():
    flat = [(10.0, 20.0), (210.0, 20.0), (210.0, 120.0), (10.0, 120.0)]
    homography = geometry._Homography.of_rect(100, 50, flat)
    assert homography.apply(50, 25) == pytest.approx((110, 70))


class _FrameSession:
    def __init__(self, border, content=None, width=400, height=300):
        self.model = {"border": border, "content": content or border}
        self.model |= {"width": width, "height": height}

    async def send(self, method, params=None, timeout=None):
        if method == "DOM.getFrameOwner":
            return {"backendNodeId": 9}
        return {"model": self.model}


@pytest.mark.parametrize(
    "border",
    [
        [100, 50, 100.2, 50, 100.2, 350, 100, 350],  # edge-on: no area
        [100, 50, 420, 350, 420, 50, 100, 350],  # folded: a bow tie
    ],
)
async def test_a_frame_seen_edge_on_or_folded_is_not_hittable(border):
    with pytest.raises(geometry.ElementNotHittableError, match="edge-on"):
        await geometry._frame_map(None, _FrameSession(border), "F1")


async def test_a_frame_map_starts_at_the_content_corner():
    border = [100, 50, 500, 50, 500, 350, 100, 350]
    content = [110, 60, 490, 60, 490, 340, 110, 340]
    owner, homography = await geometry._frame_map(None, _FrameSession(border, content), "F1")
    assert owner == 9
    assert homography.apply(0, 0) == pytest.approx((110, 60))
    assert homography.invert(120, 70) == pytest.approx((10, 10))

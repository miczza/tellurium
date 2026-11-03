"""Human clicks into an iframe drawn in 3D (perspective, ``matrix3d``) or under a CSS
zoom on an ancestor, cross-site (OOPIF) or not, and nested twice.

The framed page is a grid of buttons edge to edge (``oopif_grid.html``): a click
mapped with the wrong scale, offset or angle lands on a neighbour, which writes its
own name in ``#state``. The stage (``frame_3d.html``) has a "Delete account" button
at its (0, 0), where an unmapped point would land.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from tellurium.browser.geometry import ElementNotHittableError
from tellurium.browser.handles import StaleElementError
from tests.integration.test_snapshot_oopif import _iframe_targets, _ref_of, _snapshot_with

_PERSPECTIVE = "&perspective=400px&transform=rotateY(20deg)"
_MATRIX = "&transform=" + quote("matrix3d(1,0.05,0,0.0006,0,1,0,0.0004,0,0,1,0,0,0,0,1)")
_STAGES = {
    "perspective": _PERSPECTIVE,
    "matrix3d": _MATRIX,
    "tilted-back": "&perspective=400px&transform=rotateX(-25deg)",
    "zoomed-ancestor": "&zoom=1.5&left=60&top=40",
    "zoomed-and-perspective": "&zoom=1.5&left=60&top=40" + _PERSPECTIVE,
    # mirrored: the map turns the frame over (a negative determinant)
    "mirrored-x": "&transform=scaleX(-1)",
    "mirrored-y": "&transform=scaleY(-1)",
    "mirrored-in-perspective": "&perspective=400px&transform=" + quote("scaleX(-1) rotateY(20deg)"),
}


def _stage(server: str, src: str, query: str) -> str:
    return f"{server}/frame_3d.html?src={quote(src, safe='')}{query}"


def _other_site(local_server: str) -> str:
    return local_server.replace("127.0.0.1", "localhost")


async def _open(tab, url: str) -> str:
    await tab.get(url)
    return await _snapshot_with(tab, '- button "Xray"')


async def _clicked(tab) -> str:
    text = await tab.snapshot()
    return next(line for line in text.splitlines() if "paragraph" in line)


async def _click_each(tab, text: str, targets=("Hotel", "Lima", "Sierra")) -> None:
    for target in targets:
        button = await tab.ref(_ref_of(text, f'- button "{target}"'))
        await button.click(human=True)
        assert f'"clicked {target}"' in await _clicked(tab)
    assert await tab.eval("document.title") == "Stage"


@pytest.mark.parametrize("stage", list(_STAGES))
@pytest.mark.parametrize("site", ["cross-site", "same-site"])
async def test_human_click_in_a_3d_or_zoomed_frame_hits_its_target(
    browser, local_server, stage, site
):
    host = _other_site(local_server) if site == "cross-site" else local_server
    tab = browser.main_tab
    text = await _open(tab, _stage(local_server, f"{host}/oopif_grid.html", _STAGES[stage]))
    await _click_each(tab, text)


@pytest.mark.parametrize(
    ("outer", "inner"),
    [(_PERSPECTIVE, _MATRIX), (_MATRIX, _PERSPECTIVE), ("&zoom=1.5", _PERSPECTIVE)],
    ids=["perspective-then-matrix3d", "matrix3d-then-perspective", "zoom-then-perspective"],
)
async def test_human_click_in_a_3d_frame_inside_a_3d_frame(
    browser, local_server, other_server, outer, inner
):
    """127.0.0.1 holds localhost in 3D, which holds 127.0.0.2 in 3D: two OOPIFs."""
    grid = f"{other_server}/oopif_grid.html"
    middle = _stage(_other_site(local_server), grid, inner + "&left=10&top=10&width=400&height=240")
    tab = browser.main_tab
    text = await _open(tab, _stage(local_server, middle, outer))
    await _click_each(tab, text, ("Alpha", "Hotel", "Juliet"))


@pytest.mark.parametrize(
    ("site", "error"),
    # in the tab's own process Chrome gives the node no area at all: no box
    [("cross-site", ElementNotHittableError), ("same-site", StaleElementError)],
)
async def test_a_frame_seen_edge_on_takes_no_click(browser, local_server, site, error):
    host = _other_site(local_server) if site == "cross-site" else local_server
    tab = browser.main_tab
    url = _stage(local_server, f"{host}/oopif_grid.html", "&transform=rotateY(90deg)")
    await tab.get(url)
    text = await _snapshot_with(tab, '- button "Hotel"')
    button = await tab.ref(_ref_of(text, '- button "Hotel"'))
    with pytest.raises(error):
        await button.click(human=True)
    assert '"idle"' in await _clicked(tab)
    assert await tab.eval("document.title") == "Stage"


@pytest.fixture(scope="module")
def other_port():
    """The fixtures from 127.0.0.1 on another port: another origin, the same site, so
    the frame stays in the tab's process."""
    import http.server
    import threading

    from tests.integration.conftest import _FixtureHandler

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


async def test_a_zoomed_same_process_frame_of_another_origin_takes_the_click(
    browser, local_server, other_port
):
    """The frame's zoom is read in its own isolated world, also when its origin is not
    the root's: the click reaches each button."""
    tab = browser.main_tab
    text = await _open(
        tab, _stage(local_server, f"{other_port}/oopif_grid.html", "&zoom=1.5&left=60&top=40")
    )
    assert await _iframe_targets(tab) == []  # the premise: one process, no cross-site frame
    await _click_each(tab, text)


@pytest.mark.parametrize("stage", ["", _PERSPECTIVE])
async def test_a_same_process_frame_of_another_origin_without_zoom_takes_the_click(
    browser, local_server, other_port, stage
):
    tab = browser.main_tab
    text = await _open(tab, _stage(local_server, f"{other_port}/oopif_grid.html", stage))
    assert await _iframe_targets(tab) == []
    await _click_each(tab, text)


_GRID = [
    "Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel",
    "India", "Juliet", "Kilo", "Lima", "Mike", "November", "Oscar", "Papa", "Quebec",
    "Romeo", "Sierra", "Tango", "Uniform", "Victor", "Whiskey", "Xray",
]  # fmt: skip


@pytest.mark.parametrize(
    ("outer", "middle"),
    [
        ("&zoom=1.5", ""),
        ("&zoom=2", ""),
        ("&zoom=1.2", "&zoom=1.25"),  # zoom at two levels
        ("", "&zoom=1.5"),  # zoom only inside the same-process frame
    ],
    ids=["zoom-1.5", "zoom-2", "zoom-two-levels", "zoom-in-the-middle"],
)
async def test_human_click_in_an_oopif_inside_a_zoomed_same_process_frame(
    browser, local_server, outer, middle
):
    """127.0.0.1 (zoomed) holds 127.0.0.1 (same process), which holds localhost (an
    OOPIF): the <iframe> of the OOPIF has its box divided by the zoom of the frame
    holding it. Every button of the grid gets its own click, or none is sent."""
    grid = f"{_other_site(local_server)}/oopif_grid.html"
    inner = _stage(local_server, grid, middle + "&left=0&top=0&width=420&height=190")
    tab = browser.main_tab
    text = await _open(
        tab, _stage(local_server, inner, outer + "&left=10&top=10&width=560&height=280")
    )
    # the premise: only the grid is cross-site (an iframe target of its own)
    targets = await _iframe_targets(tab)
    assert [url for url in targets if "oopif_grid" in url] and len(targets) == 1
    await _click_each(tab, text, _GRID)


@pytest.mark.parametrize("outer", ["&zoom=1.5", "&zoom=2"])
async def test_human_click_in_an_oopif_inside_a_zoomed_frame_of_another_origin(
    browser, local_server, other_port, outer
):
    """127.0.0.1 (zoomed) holds 127.0.0.1 on another port (same process, another
    origin), which holds localhost (an OOPIF)."""
    grid = f"{_other_site(local_server)}/oopif_grid.html"
    inner = _stage(other_port, grid, "&left=0&top=0&width=420&height=190")
    tab = browser.main_tab
    url = _stage(local_server, inner, outer + "&left=10&top=10&width=560&height=280")
    text = await _open(tab, url)
    assert len(await _iframe_targets(tab)) == 1
    await _click_each(tab, text, _GRID)

"""A2 part C — clicks into a cross-site iframe (OOPIF) that is transformed or zoomed.

The widget is a grid of buttons edge to edge (``oopif_grid.html``): a click mapped
with the wrong scale, offset or angle lands on a neighbour, which writes its own
name in ``#state``. The host's iframe has a border and a padding, and a "Delete
account" button at (0, 0) of the host.
"""

from __future__ import annotations

import math

import pytest

from tellurium.browser.geometry import ElementNotHittableError, content_box
from tests.integration.test_snapshot_oopif import _ref_of, _snapshot_with

# The <iframe> of oopif_host.html: left/top 360/140, border 4, padding 6, 440x300.
_FRAME = (360, 140, 460, 320)
_CONTENT = (370, 150)


async def _open_grid(tab, local_server: str, query: str) -> str:
    await tab.get(f"{local_server}/oopif_host.html?page=oopif_grid.html{query}")
    return await _snapshot_with(tab, '- button "Xray"')


async def _clicked(tab) -> str:
    text = await tab.snapshot()
    return next(line for line in text.splitlines() if "paragraph" in line)


@pytest.mark.parametrize(
    "query",
    [
        "&transform=scale(.5)&origin=0 0",
        "&transform=scale(.5)",
        "&transform=rotate(15deg)",
        "&transform=translate(-120px,40px) scale(.75)",
        "&transform=rotate(-10deg) scale(1.2)&zoom=0.8",
        "&zoom=1.5",
        "",
    ],
)
@pytest.mark.parametrize("target", ["Hotel", "Lima", "Sierra"])
async def test_human_click_in_a_transformed_oopif_hits_its_target(
    browser, local_server, query, target
):
    tab = browser.main_tab
    text = await _open_grid(tab, local_server, query)
    button = await tab.ref(_ref_of(text, f'- button "{target}"'))
    await button.click(human=True)
    assert f'"clicked {target}"' in await _clicked(tab)
    await button.hover()
    assert await tab.eval("document.title") == "Host"


async def test_box_of_a_scaled_oopif_is_scaled(browser, local_server):
    tab = browser.main_tab
    text = await _open_grid(tab, local_server, "&transform=scale(.5)&origin=0 0")
    box = await content_box(await tab.ref(_ref_of(text, '- button "Alpha"')))
    # origin 0 0 is the border box's corner: the content starts at half the 10 px inset
    assert box["x"] == pytest.approx(_FRAME[0] + (10 + 10) / 2, abs=1)
    assert box["y"] == pytest.approx(_FRAME[1] + (10 + 10) / 2, abs=1)
    assert (box["width"], box["height"]) == pytest.approx((35, 20), abs=1)


async def test_box_of_a_rotated_oopif_holds_the_turned_button(browser, local_server):
    tab = browser.main_tab
    text = await _open_grid(tab, local_server, "&transform=rotate(15deg)")
    box = await content_box(await tab.ref(_ref_of(text, '- button "Alpha"')))
    # the bounding box of a 70x40 rectangle turned by 15 degrees
    angle = math.radians(15)
    width = 70 * math.cos(angle) + 40 * math.sin(angle)
    height = 70 * math.sin(angle) + 40 * math.cos(angle)
    assert (box["width"], box["height"]) == pytest.approx((width, height), abs=1)


@pytest.mark.parametrize(
    "query", ["&transform=perspective(300px) rotateY(35deg)", "&transform=rotateY(90deg)"]
)
async def test_oopif_in_perspective_is_not_hittable(browser, local_server, query):
    """No affine map takes the widget's points to the screen: nothing is sent."""
    tab = browser.main_tab
    text = await _open_grid(tab, local_server, query)
    button = await tab.ref(_ref_of(text, '- button "Hotel"'))
    with pytest.raises(ElementNotHittableError):
        await button.click(human=True)
    with pytest.raises(ElementNotHittableError):
        await button.hover()
    assert '"idle"' in await _clicked(tab)
    assert await tab.eval("document.title") == "Host"

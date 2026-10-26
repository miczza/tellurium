"""Tab.screenshot(full_page=True) captures the whole page at its CSS size and
leaves the page as it was (P1)."""

import base64
import json
import os
import struct

import pytest

pytestmark = pytest.mark.asyncio

# what the page can see of its own layout
_LAYOUT = "[document.documentElement.clientWidth, innerWidth, innerHeight, scrollY]"
_BLUE, _RED, _WHITE = [0, 0, 255], [255, 0, 0], [255, 255, 255]


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


async def _pixel(tab, png: bytes, x: int, y: int) -> list[int]:
    """RGB of (x, y) in *png*, decoded by the page's own canvas."""
    url = json.dumps("data:image/png;base64," + base64.b64encode(png).decode())
    rgba = await tab.eval(
        f"""(async () => {{
            const img = new Image();
            img.src = {url};
            await img.decode();
            const canvas = document.createElement('canvas');
            canvas.width = img.width;
            canvas.height = img.height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0);
            return Array.from(ctx.getImageData({x}, {y}, 1, 1).data);
        }})()""",
        timeout=10,
    )
    return rgba[:3]


async def _emulate(tab, ratio):
    await tab.send_cdp(
        "Emulation.setDeviceMetricsOverride",
        {"width": 800, "height": 600, "deviceScaleFactor": ratio, "mobile": False},
    )


async def _check_full_page(tab):
    """A full page capture: CSS size, bottom and right edge in it, page unchanged."""
    before = await tab.eval(_LAYOUT)
    png = await tab.screenshot(full_page=True, timeout=10)
    assert await tab.eval(_LAYOUT) == before  # the scrollbar is back, nothing moved
    width, height = _png_size(png)
    # the capture lays the page out at its full height: no vertical scrollbar
    assert (width, height) == (before[1], 4000)
    assert await _pixel(tab, png, width // 2, height - 10) == _RED
    assert await _pixel(tab, png, width - 3, 50) == _BLUE  # the right edge is in
    assert await _pixel(tab, png, width // 2, 10) == _WHITE
    return png


@pytest.mark.parametrize("ratio", [1, 2])
async def test_full_page_has_the_whole_page_at_css_size(browser, local_server, ratio):
    tab = await browser.get(local_server + "/tall_block.html")
    await _emulate(tab, ratio)
    assert await tab.eval("window.devicePixelRatio") == ratio
    await tab.eval("scrollTo(0, 1000)")
    first = await _check_full_page(tab)
    assert _png_size(await _check_full_page(tab)) == _png_size(first)  # same again


async def test_full_page_without_emulation_restores_the_scrollbar(any_browser, local_server):
    tab = await any_browser.get(local_server + "/tall_block.html")
    width, inner = await tab.eval("[document.documentElement.clientWidth, innerWidth]")
    assert width < inner  # the premise: a vertical scrollbar takes room
    await _check_full_page(tab)


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs a display (xvfb-run)")
async def test_headed_fractional_device_pixel_ratio_keeps_the_css_size(local_server):
    """Headed, an emulated ratio of 2 reads 2.0000000298 and CDP floors the content
    size (984 for 985): the image still has the page's CSS width."""
    from tellurium import Browser

    browser = await Browser.launch(headless=False)
    try:
        tab = await browser.get(local_server + "/tall_block.html")
        await _emulate(tab, 2)
        await _check_full_page(tab)
    finally:
        await browser.close()


async def test_viewport_screenshot_is_unchanged(browser, local_server):
    tab = await browser.get(local_server + "/tall_block.html")
    await _emulate(tab, 1)
    assert _png_size(await tab.screenshot()) == (800, 600)

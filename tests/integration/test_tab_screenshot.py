"""Tab.screenshot(full_page=True) captures the whole page at its CSS size (P1)."""

import base64
import json
import struct

import pytest

pytestmark = pytest.mark.asyncio


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


async def _pixel(tab, png: bytes, x: int, y: int) -> list[int]:
    """RGBA of (x, y) in *png*, decoded by the page's own canvas."""
    url = json.dumps("data:image/png;base64," + base64.b64encode(png).decode())
    return await tab.eval(
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


@pytest.mark.parametrize("ratio", [1, 2])
async def test_full_page_has_the_bottom_of_the_page_at_css_size(browser, local_server, ratio):
    tab = await browser.get(local_server + "/tall_block.html")
    await tab.send_cdp(
        "Emulation.setDeviceMetricsOverride",
        {"width": 800, "height": 600, "deviceScaleFactor": ratio, "mobile": False},
    )
    assert await tab.eval("window.devicePixelRatio") == ratio
    page_width = await tab.eval("document.documentElement.scrollWidth")
    png = await tab.screenshot(full_page=True, timeout=10)
    width, height = _png_size(png)
    assert (width, height) == (page_width, 4000)
    assert (await _pixel(tab, png, width // 2, height - 10))[:3] == [255, 0, 0]
    assert (await _pixel(tab, png, width // 2, 10))[:3] == [255, 255, 255]


async def test_viewport_screenshot_is_unchanged(browser, local_server):
    tab = await browser.get(local_server + "/tall_block.html")
    await tab.send_cdp(
        "Emulation.setDeviceMetricsOverride",
        {"width": 800, "height": 600, "deviceScaleFactor": 1, "mobile": False},
    )
    assert _png_size(await tab.screenshot()) == (800, 600)

"""Tab.screenshot(full_page=True) captures the whole page at its CSS size and
leaves the page as it was (P1)."""

import base64
import json
import struct

import pytest

from tests.platform_marks import needs_display

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


@needs_display
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


_FRAMES = "new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


async def scrolled_body_scroller(tab, server):
    """``html, body {height: 100%}`` and ``body {overflow-y: auto}``, scrolled to 1000:
    turning <html>'s overflow off there would make <body> the scroller (scrollY 0)."""
    await tab.get(server + "/body_scroller.html")
    size = None
    for _ in range(50):  # a loaded machine may still be sizing the window
        if size == (size := await tab.eval("[innerWidth, innerHeight]")):
            break
        await tab.eval(_FRAMES)
    scrolled = (
        "new Promise(r => { addEventListener('scroll', r, {once: true}); scrollTo(0, 1000) })"
    )
    await tab.eval(scrolled, timeout=10)
    await tab.eval(_FRAMES)
    await tab.eval("window.scrolls = 0")
    return await tab.eval(_LAYOUT)


async def check_left_alone(tab, before):
    await tab.eval(_FRAMES)
    assert await tab.eval(_LAYOUT) == before  # scrollbar there, scrollY still 1000
    assert await tab.eval("window.scrolls") == 0  # and the page saw no scroll


async def test_full_page_leaves_a_scrolled_body_scroller_alone(any_browser, local_server):
    tab = any_browser.main_tab
    before = await scrolled_body_scroller(tab, local_server)
    assert before[3] == 1000 and before[0] < before[1]  # the premise
    for _ in range(2):
        png = await tab.screenshot(full_page=True, timeout=10)
        assert _png_size(png)[1] == 4000
        await check_left_alone(tab, before)


_QUIRKS_LAYOUT = (
    "[document.scrollingElement.clientWidth, innerWidth, document.scrollingElement.clientHeight,"
    " innerHeight, scrollY, document.compatMode]"
)


async def test_full_page_of_a_quirks_mode_page_gives_the_scrollbar_back(any_browser, local_server):
    """No doctype: <html>'s clientHeight is the document's, so the viewport's gaps are
    measured on ``document.scrollingElement`` (<body> there). P1, round 4."""
    tab = any_browser.main_tab
    await tab.get(local_server + "/quirks.html")
    await tab.eval(_FRAMES)
    scrolled = (
        "new Promise(r => { addEventListener('scroll', r, {once: true}); scrollTo(0, 1000) })"
    )
    await tab.eval(scrolled, timeout=10)
    await tab.eval(_FRAMES)
    await tab.eval("window.scrolls = 0")
    before = await tab.eval(_QUIRKS_LAYOUT)
    assert before[5] == "BackCompat" and before[0] < before[1] and before[4] == 1000
    for _ in range(2):
        png = await tab.screenshot(full_page=True, timeout=10)
        assert _png_size(png)[1] == 4000
        await tab.eval(_FRAMES)
        assert await tab.eval(_QUIRKS_LAYOUT) == before
        assert await tab.eval("window.scrolls") == 0


async def test_viewport_screenshot_is_unchanged(browser, local_server):
    tab = await browser.get(local_server + "/tall_block.html")
    await _emulate(tab, 1)
    assert _png_size(await tab.screenshot()) == (800, 600)


async def test_cancelled_mid_capture_the_scrollbar_still_comes_back(browser, local_server):
    """Cancelled while Chrome captures: the scrollbar is given back once it answers,
    by a task of the tab that ends then (P1, round 3)."""
    import asyncio

    tab = await browser.get(local_server + "/tall_block.html")
    await tab.eval("document.body.firstElementChild.style.height = '60000px'")
    before = await tab.eval(_LAYOUT)
    started, send = asyncio.Event(), tab._session.send

    async def spy(method, params=None, **kwargs):
        if method == "Page.captureScreenshot":
            started.set()
        return await send(method, params, **kwargs)

    tab._session.send = spy
    shot = asyncio.ensure_future(tab.screenshot(full_page=True, timeout=60))
    await asyncio.wait_for(started.wait(), 10)
    await asyncio.sleep(0.05)
    shot.cancel()
    with pytest.raises(asyncio.CancelledError):
        await shot
    pending = set(tab._background)
    assert pending  # Chrome is still capturing: the tab restores once it answers
    await asyncio.wait_for(asyncio.gather(*pending), 60)
    await tab.eval(_FRAMES)
    assert await tab.eval(_LAYOUT) == before
    assert tab._background == set()


# tall_block.html's body, built in the tab's first document (no navigation at all; the
# document may ask for Trusted Types, so no innerHTML)
_TALL_BODY = """(() => {
  const box = (css) => Object.assign(document.createElement('div'), {style: css});
  const page = box('position:relative;height:4000px;background:#fff');
  page.append(box('position:absolute;top:0;right:0;width:10px;height:100px;background:#00f'));
  page.append(box('position:absolute;left:0;right:0;bottom:0;height:200px;background:#f00'));
  document.body.style.margin = '0';
  document.body.replaceChildren(page);
  return location.href;
})()"""


@pytest.mark.parametrize("ratio", [None, 2])
async def test_full_page_before_the_first_navigation_is_like_after_it(browser, ratio):
    """No navigation yet, so no main frame id known from one: the capture still has the
    CSS size and gives the scrollbar back (P3 [10])."""
    tab = browser.main_tab
    await tab.eval(_TALL_BODY)
    if ratio:
        await _emulate(tab, ratio)
    else:
        width, inner = await tab.eval("[document.documentElement.clientWidth, innerWidth]")
        assert width < inner  # the premise: a vertical scrollbar takes room
    assert tab._frame_id == ""  # the premise: no Page.frameNavigated seen
    await _check_full_page(tab)

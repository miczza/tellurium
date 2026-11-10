"""eval_on, screenshot and pdf take a per-call timeout (R1-A adversary, minor).

The session default is lowered so the scenarios stay short: without the
parameter the call is cut at the default, with it the call completes.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from tests.timeout_scale import scaled

pytestmark = pytest.mark.asyncio

SLOW = "() => new Promise(r => setTimeout(() => r('done'), 1500))"


@pytest.fixture
async def page(browser, local_server):
    tab = await browser.get(local_server + "/basic.html")
    default = browser._router.default_timeout  # scaled on the slow runners
    browser._router.default_timeout = 0.5
    yield tab
    browser._router.default_timeout = default


async def test_eval_on_is_cut_at_the_session_default(page):
    with pytest.raises(asyncio.TimeoutError):
        await page.eval_on("body", SLOW)


async def test_eval_on_timeout_extends_one_call(page):
    assert await page.eval_on("body", SLOW, timeout=scaled(10)) == "done"


async def test_eval_on_timeout_can_also_shorten_it(page):
    page._browser._router.default_timeout = scaled(30.0)
    start = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await page.eval_on("body", SLOW, timeout=0.3)
    assert time.monotonic() - start < 1.2


async def test_screenshot_and_pdf_take_a_timeout(page, tmp_path):
    page._browser._router.default_timeout = 0.0001  # nothing answers that fast
    png = await page.screenshot(str(tmp_path / "shot.png"), full_page=True, timeout=scaled(10))
    assert png.startswith(b"\x89PNG") and (tmp_path / "shot.png").read_bytes() == png
    pdf = await page.pdf(str(tmp_path / "page.pdf"), timeout=scaled(10), landscape=True)
    assert pdf.startswith(b"%PDF") and (tmp_path / "page.pdf").read_bytes() == pdf

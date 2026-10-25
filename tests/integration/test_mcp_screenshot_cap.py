"""The MCP screenshot tool against a real Chrome: a page of random pixels whose
full-page PNG is far over the 5 MB cap comes back as a JPEG under it, said in
the result; a small page stays PNG."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from tellurium.mcp import pages, screenshots  # noqa: E402


class _Pool:
    def __init__(self, tab):
        self._tab = tab

    def tab(self, target_id):
        return self._tab


async def _noise_tab(browser, local_server):
    tab = await browser.get(f"{local_server}/noise.html")
    for _ in range(100):
        if await tab.eval("document.title") == "Noise ready":
            return tab
        await asyncio.sleep(0.1)
    raise AssertionError("the noise page never drew")


async def test_full_page_over_the_cap_comes_back_as_a_jpeg_under_it(browser, local_server):
    tab = await _noise_tab(browser, local_server)
    capture, _, _ = await pages._full_page(tab)
    png = await capture("png", None, 1.0)
    assert screenshots.encoded_size(len(png)) > screenshots.SHOT_BYTES  # the premise

    reply = await pages._screenshot(_Pool(tab), {"targetId": "t1", "fullPage": True})
    assert reply.image_type == "image/jpeg" and reply.image[:2] == b"\xff\xd8"
    assert screenshots.encoded_size(len(reply.image)) <= screenshots.SHOT_BYTES
    assert reply.data["format"] == "jpeg"
    assert "over the 5.0 MB cap" in reply.text


async def test_viewport_over_a_lower_cap_is_scaled(browser, local_server, monkeypatch):
    tab = await _noise_tab(browser, local_server)
    monkeypatch.setattr(screenshots, "SHOT_BYTES", 150_000)
    reply = await pages._screenshot(_Pool(tab), {"targetId": "t1"})
    assert reply.image_type == "image/jpeg"
    assert screenshots.encoded_size(len(reply.image)) <= 150_000
    assert reply.data["scale"] < 1 and "scale" in reply.text


async def test_ref_over_a_lower_cap_is_a_jpeg_of_that_element(browser, local_server, monkeypatch):
    tab = await _noise_tab(browser, local_server)
    snapshot = await tab.snapshot()
    ref = next(
        line.split("[ref=")[1].split("]")[0] for line in snapshot.splitlines() if "[ref=" in line
    )
    monkeypatch.setattr(screenshots, "SHOT_BYTES", 400_000)
    assert 'image "noise"' in next(line for line in snapshot.splitlines() if f"ref={ref}]" in line)
    reply = await pages._screenshot(_Pool(tab), {"targetId": "t1", "ref": ref})
    assert reply.image_type == "image/jpeg" and reply.image[:2] == b"\xff\xd8"
    assert screenshots.encoded_size(len(reply.image)) <= 400_000


async def test_small_page_stays_png(browser, local_server):
    tab = await browser.get(f"{local_server}/basic.html")
    reply = await pages._screenshot(_Pool(tab), {"targetId": "t1"})
    assert reply.image_type == "image/png" and reply.image[:4] == b"\x89PNG"
    assert reply.data["format"] == "png" and "cap" not in reply.text

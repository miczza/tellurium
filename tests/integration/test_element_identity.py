"""An Element must stay usable after later queries on the same tab.

Every Tab query refreshes the DOM agent's document (``DOM.getDocument``),
which invalidates previously handed-out nodeIds. Elements must therefore
not depend on nodeIds that outlive the query that produced them.
"""

from __future__ import annotations

import pytest


@pytest.fixture
async def page(browser, local_server):
    return await browser.new_tab(f"{local_server}/upload.html")


async def test_text_after_a_later_select(page):
    heading = await page.select("#heading")
    await page.select("#note")
    assert await heading.text() == "Upload"


async def test_html_after_a_later_select(page):
    heading = await page.select("#heading")
    await page.select("#note")
    assert await heading.html() == '<h1 id="heading" data-role="title">Upload</h1>'


async def test_attributes_after_a_later_select(page):
    heading = await page.select("#heading")
    await page.select("#note")
    assert await heading.attributes() == {"id": "heading", "data-role": "title"}


async def test_select_all_items_after_a_later_xpath(page):
    first, *_ = await page.select_all("h1, p")
    await page.xpath("//p")
    assert await first.text() == "Upload"


async def test_xpath_result_after_a_later_select(page):
    note = await page.xpath("//p[@id='note']")
    await page.select("#heading")
    assert await note.text() == "Pick a file"


async def test_find_result_after_a_later_select(page):
    note = await page.find("Pick a file")
    await page.select("#heading")
    assert await note.attr("id") == "note"


async def test_upload_after_a_later_select(page, tmp_path):
    payload = tmp_path / "hello.txt"
    payload.write_text("hi")
    file_input = await page.select("#file")
    await page.select("#note")
    await file_input.upload(str(payload))
    assert await page.eval("document.getElementById('file').files[0].name") == "hello.txt"


async def test_focus_after_a_later_select(page):
    file_input = await page.select("#file")
    await page.select("#note")
    await file_input.focus()
    assert await page.eval("document.activeElement.id") == "file"


async def test_relative_select_after_a_later_select(page):
    body = await page.select("body")
    await page.select("#note")
    heading = await body.select("h1")
    assert await heading.attr("id") == "heading"

"""Element tree/text/relative-query API against real Chrome."""
from __future__ import annotations

import pytest


@pytest.fixture
async def tree(browser, local_server):
    return await browser.new_tab(f"{local_server}/tree.html")


async def test_text_excludes_nested_elements(tree):
    price = await tree.select("#card-1 .price")
    assert await price.text() == "Price"


async def test_text_all_includes_the_whole_subtree(tree):
    price = await tree.select("#card-1 .price")
    assert await price.text_all() == "Price 9.99"


async def test_text_and_text_all_agree_on_a_leaf(tree):
    heading = await tree.select("#card-1 h3")
    assert await heading.text() == "Widget"
    assert await heading.text_all() == "Widget"


async def test_own_text_is_an_alias(tree):
    price = await tree.select("#card-1 .price")
    assert await price.own_text() == await price.text()


async def test_children_returns_direct_element_children(tree):
    card = await tree.select("#card-1")
    tags = [await c.tag() for c in await card.children()]
    assert tags == ["h3", "p", "a"]


async def test_children_of_an_empty_element(tree):
    empty = await tree.select("#empty")
    assert await empty.children() == []


async def test_parent_walks_up_the_tree(tree):
    heading = await tree.select("#card-1 h3")
    card = await heading.parent()
    assert await card.attr("id") == "card-1"
    section = await card.parent()
    assert await section.attr("id") == "products"


async def test_relative_find_is_scoped_to_the_element(tree):
    card = await tree.select("#card-2")
    link = await card.find("Buy now")
    assert await link.attr("href") == "/buy/2"


async def test_relative_find_all_only_sees_descendants(tree):
    card = await tree.select("#card-1")
    assert len(await card.find_all("Buy now")) == 1
    section = await tree.select("#products")
    assert len(await section.find_all("Buy now")) == 2


async def test_relative_xpath_uses_the_element_as_context(tree):
    card = await tree.select("#card-2")
    price = await card.xpath(".//b")
    assert await price.text() == "19.99"


async def test_relative_xpath_all(tree):
    section = await tree.select("#products")
    prices = await section.xpath_all(".//p[@class='price']/b")
    assert [await p.text() for p in prices] == ["9.99", "19.99"]


async def test_relative_xpath_returns_none_when_unmatched(tree):
    card = await tree.select("#card-1")
    assert await card.xpath(".//table") is None


async def test_typing_with_typos_still_produces_the_exact_text(tree):
    field = await tree.select("#typed")
    await field.type("hello world", human=True, typos=True, wpm=900)
    assert await tree.eval("document.getElementById('typed').value") == "hello world"

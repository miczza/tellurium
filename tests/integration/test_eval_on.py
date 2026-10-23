"""Tab.eval_on hands the element to arrow functions too (they have no `this`)."""

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def page(browser, local_server):
    return await browser.get(local_server + "/basic.html")


@pytest.mark.parametrize(
    "expression",
    [
        "el => el.id",
        "(el) => el.id",
        "(el) => { return el.id; }",
        "function(el) { return el.id; }",
        "function() { return this.id; }",
    ],
)
async def test_eval_on_gets_the_element(page, expression):
    assert await page.eval_on("#content", expression) == "content"


async def test_eval_on_arrow_with_a_promise(page):
    assert await page.eval_on("#link", "async el => el.tagName") == "A"

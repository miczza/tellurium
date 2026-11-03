"""Tab.eval_on runs functions, expressions and bodies with the element (R1-C).

Every form gets the element as ``this`` and, when it is a function, as its
argument; a JavaScript exception is a Python error, never a silent ``None``.
"""

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def page(browser, local_server):
    return await browser.get(local_server + "/basic.html")


@pytest.mark.parametrize(
    "expression",
    [
        # forms the adversary found broken by the old '=>' rewriting
        "(el => el.id)",
        "((el) => el.id)",
        "(function(el){ return [1].map(x => x) && el.id })",
        "async(el) => el.id",
        "(el, f = x => x) => f(el.id)",
        # arrows, functions, expressions and bodies
        "() => this.id",
        "el => el.id",
        "(el) => el.id",
        "(el) => { return el.id; }",
        "async el => el.id",
        "async () => this.id",
        "function(el) { return el.id; }",
        "function(){ return this.id }",
        "return this.id",
        "this.id",
        "el => el.id // trailing comment",
        "el => ({id: el.id}).id",
    ],
)
async def test_eval_on_gets_the_element(page, expression):
    assert await page.eval_on("#content", expression) == "content"


async def test_eval_on_awaits_a_promise(page):
    assert await page.eval_on("#link", "async el => el.tagName") == "A"


@pytest.mark.parametrize(
    "expression",
    [
        "el => { throw new Error('boom') }",
        "async el => { throw new Error('boom') }",
        "throw new Error('boom')",
    ],
)
async def test_a_javascript_exception_is_raised(page, expression):
    with pytest.raises(RuntimeError, match="boom"):
        await page.eval_on("#content", expression)


async def test_a_syntax_error_is_raised(page):
    with pytest.raises(RuntimeError, match="SyntaxError"):
        await page.eval_on("#content", "el => {")


async def test_a_function_runs_once(page):
    await page.eval_on("#content", "el => { el.dataset.n = (+el.dataset.n || 0) + 1 }")
    assert await page.eval_on("#content", "el => el.dataset.n") == "1"


_COUNT = "window.count = (window.count || 0) + 1"


@pytest.mark.parametrize(
    "expression",
    [
        # an exception whose description itself throws (P1)
        f"({_COUNT}, (() => {{ throw Object.create(null) }})())",
        f"el => {{ {_COUNT}; throw Object.create(null) }}",
        f"{_COUNT}; throw Object.create(null)",
        f"{_COUNT}; throw new Proxy({{}}, {{ get() {{ throw 1 }} }})",
        # a SyntaxError thrown at run time is not a compile error
        f"el => {{ {_COUNT}; JSON.parse('{{') }}",
        f"({_COUNT}, JSON.parse('{{'))",
    ],
)
async def test_a_throwing_expression_runs_once(page, expression):
    with pytest.raises(RuntimeError, match=r"eval_on\('#content'\) failed"):
        await page.eval_on("#content", expression)
    assert await page.eval("window.count") == 1


async def test_a_body_can_await(page):
    body = "await new Promise(r => setTimeout(r, 10)); return this.id"
    assert await page.eval_on("#content", body) == "content"


@pytest.mark.parametrize(
    "expression",
    [
        # the value throws while Chrome serializes it (P1, round 3)
        f"el => {{ {_COUNT}; return {{ get x() {{ throw new SyntaxError('x') }} }} }}",
        f"el => {{ {_COUNT}; return new Proxy({{}}, {{ ownKeys() {{ throw 1 }} }}) }}",
    ],
)
async def test_a_value_that_throws_when_returned_is_a_runtime_error(page, expression):
    with pytest.raises(RuntimeError, match=r"eval_on\('#content'\) failed"):
        await page.eval_on("#content", expression)
    assert await page.eval("window.count") == 1


async def test_another_internal_error_is_the_cdp_error(page):
    """Only a value Chrome fails to serialize is a ``RuntimeError``: any other -32603
    of ``Runtime.callFunctionOn`` comes out as Chrome gave it (P3 [11])."""
    from tellurium.cdp.types import CDPError

    send = page._session.send

    async def failing(method, params=None, **kwargs):
        if method == "Runtime.callFunctionOn":
            raise CDPError("Internal error", -32603)
        return await send(method, params, **kwargs)

    page._session.send = failing
    try:
        with pytest.raises(CDPError) as raised:
            await page.eval_on("#content", "el => el.id")
    finally:
        page._session.send = send
    assert not isinstance(raised.value, RuntimeError) and raised.value.code == -32603


@pytest.mark.parametrize(
    "expression",
    [
        "el => { const a = {}; a.a = a; return a }",  # Chrome refuses: not a JS exception
        "el => 10n",
    ],
)
async def test_a_value_chrome_cannot_return_stays_a_cdp_error(page, expression):
    from tellurium.cdp.types import CDPError

    with pytest.raises(CDPError):
        await page.eval_on("#content", expression)
    assert await page.eval_on("#content", "el => el.id") == "content"  # the tab still works

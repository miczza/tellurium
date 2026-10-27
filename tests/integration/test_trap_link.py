"""``Element.is_trap_link`` / ``trap_link.reasons`` against real Chrome.

``trap_links.html`` holds one link per honeypot pattern, each isolating a single
signal, and normal links that look like them (the false positives to avoid). The
page counts every main-world call the check could make: it must make none.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from tellurium.stealth import trap_link

TRAPS = {
    "trap-display": ["not-rendered"],
    "trap-menu-closed": ["not-rendered"],
    "trap-details": ["not-rendered"],
    "trap-visibility": ["visibility-hidden"],
    "trap-opacity": ["transparent"],
    "trap-zero": ["zero-size"],
    "trap-1px": ["zero-size"],
    "trap-scale": ["zero-size"],
    "trap-left": ["off-page"],
    "trap-top": ["off-page"],
    "trap-right": ["off-page"],
    "trap-fixed-off": ["off-page"],
    "trap-clipped": ["clipped"],
    "trap-clip-path": ["clipped"],
    "trap-circle": ["clipped"],
    "trap-ellipse": ["clipped"],
    "trap-polygon": ["clipped"],
    "trap-empty": ["empty"],
    "trap-indent": ["empty"],
    "trap-white": ["same-color"],
    "trap-beige": ["same-color"],
    "trap-transparent-text": ["same-color"],
    "trap-aria": ["aria-hidden"],
    "trap-inert": ["inert"],
    "trap-pointer": ["no-pointer"],
    "trap-marker": ["honeypot-marker"],
    "trap-nofollow": ["not-rendered", "nofollow"],
}

NORMAL = [
    "ok-plain",
    "ok-nav",
    "ok-fixed",
    "ok-nofollow",
    "ok-image",
    "ok-icon",
    "ok-icon-font",
    "ok-button",
    "ok-gray",
    "ok-honey",
    "ok-block",
    "ok-overflow",
    "ok-logo",
    "ok-round",
    "ok-hero",
    "ok-hero-shade",
    "ok-triangle",
    "ok-scroller",
    "ok-slide-first",
    "ok-slide-last",
    "ok-slide-wide",
    "ok-menu-open",
    "ok-details-open",
    "ok-skip",
    "ok-sr-skip",
    "ok-below-fold",
]


@pytest.fixture
async def page(browser, local_server):
    return await browser.new_tab(f"{local_server}/trap_links.html")


async def _reasons(tab, ids):
    return {link: await trap_link.reasons(await tab.select(f"#{link}")) for link in ids}


async def test_every_trap_is_caught_by_its_own_signal(page):
    assert await _reasons(page, TRAPS) == TRAPS


async def test_no_normal_link_is_a_trap(page):
    assert await _reasons(page, NORMAL) == {link: [] for link in NORMAL}


async def test_is_trap_link_agrees_with_reasons(page):
    for link in [*TRAPS, *NORMAL]:
        expected = link in TRAPS
        assert await (await page.select(f"#{link}")).is_trap_link() is expected, link


async def test_the_check_leaves_no_trace_in_the_page(page):
    globals_, html = "JSON.stringify(Object.keys(window))", "document.documentElement.outerHTML"
    before, markup = await page.eval(globals_), await page.eval(html)
    mutations = await page.eval("window.__mutations")  # the parser's, so far
    for link in [*TRAPS, *NORMAL]:
        await (await page.select(f"#{link}")).is_trap_link()
    assert await page.eval("window.__touched") == 0
    assert await page.eval("window.__mutations") == mutations
    assert await page.eval(globals_) == before
    assert await page.eval(html) == markup


async def test_a_menu_link_is_a_trap_until_the_menu_opens(page):
    link = await page.select("#trap-menu-closed")
    assert await link.is_trap_link() is True
    await page.eval("document.querySelector('.menu-closed').className = 'menu-open'")
    assert await link.is_trap_link() is False


async def test_the_check_runs_again_after_a_navigation(page, local_server):
    await page.get(f"{local_server}/trap_links.html?again")
    assert await trap_link.reasons(await page.select("#trap-aria")) == ["aria-hidden"]
    assert await trap_link.reasons(await page.select("#ok-plain")) == []


async def _framed(tab, name):
    for _ in range(50):
        text = await tab.snapshot()
        for line in text.splitlines():
            if f'link "{name}"' in line and (match := re.search(r"\[ref=(e\d+)\]", line)):
                return await tab.ref(match.group(1))
        await asyncio.sleep(0.1)
    raise AssertionError(f"no link {name!r} in:\n{text}")


@pytest.mark.parametrize("query", ["", "?oopif"], ids=["same-site", "oopif"])
async def test_a_link_inside_a_frame_is_checked_in_that_frame(browser, local_server, query):
    tab = browser.main_tab
    await tab.get(f"{local_server}/trap_frame.html{query}")
    visible, away = await _framed(tab, "Visible link"), await _framed(tab, "Hidden away")
    assert await trap_link.reasons(visible) == []
    assert await trap_link.reasons(away) == ["off-page"]
    assert await trap_link.reasons(await _framed(tab, "Skip in the frame")) == []
    assert await visible.apply("function () { return window.__touched; }") == 0


async def test_without_an_isolated_world_the_check_refuses_to_run(page, monkeypatch):
    import tellurium.browser.refs as refs

    async def no_world(*_args, **_kwargs):
        return None

    monkeypatch.setattr(refs, "frame_world", no_world)
    with pytest.raises(trap_link.NoIsolatedWorldError):
        await trap_link.reasons(await page.select("#trap-left"))
    assert await page.eval("window.__touched") == 0


async def test_reach_is_that_of_the_box_that_scrolls(browser, local_server):
    """An app scrolling in its own box under a root that never scrolls (``html, body
    {overflow: hidden}``): what that box, or a fixed sidebar, scrolls to is on the page."""
    tab = await browser.new_tab(f"{local_server}/trap_spa.html")
    links = ["ok-spa-top", "ok-spa-slide", "ok-spa-below", "ok-side-below"]
    links += ["trap-spa-before", "trap-spa-outside"]
    expected = {link: ["off-page"] if link.startswith("trap") else [] for link in links}
    assert await _reasons(tab, links) == expected


FOCUS_TRAPS = {
    "trap-left": ["off-page"],
    "trap-opacity": ["transparent"],
    "trap-font": ["zero-size"],
    "trap-unfocusable": ["off-page"],
    "trap-animated": ["off-page"],
}
FOCUS_NORMAL = ["ok-skip", "ok-sr-skip", "ok-within", "ok-fade"]


async def test_only_a_focus_rule_that_brings_the_link_back_reveals_it(browser, local_server):
    """``a:focus { transform: translateY(-1px) }`` touches a property on every link but
    brings none back: the focused state is looked at, not the rule. A transition on the
    way back (or a link out of the tab order) leaves it a trap: no event is fired."""
    tab = await browser.new_tab(f"{local_server}/trap_focus.html")
    await tab.eval("window.scrollTo(0, 120)")
    frames = "new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
    await tab.eval(frames)  # the scroll event of scrollTo itself
    await tab.eval("window.__events.length = 0")
    page = "[document.activeElement.tagName, scrollX, scrollY]"
    before = await tab.eval(page)
    expected = FOCUS_TRAPS | {link: [] for link in FOCUS_NORMAL}
    assert await _reasons(tab, expected) == expected
    assert await tab.eval(page) == before
    await tab.eval(frames)
    assert await tab.eval("window.__events") == []
    assert await tab.eval("window.__touched") == 0
    assert await tab.eval("getComputedStyle(document.getElementById('ok-skip')).left") == "-9999px"

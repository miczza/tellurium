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
    "ok-triangle",
    "ok-scroller",
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
    assert await visible.apply("function () { return window.__touched; }") == 0


async def test_without_an_isolated_world_the_check_refuses_to_run(page, monkeypatch):
    import tellurium.browser.refs as refs

    async def no_world(*_args, **_kwargs):
        return None

    monkeypatch.setattr(refs, "frame_world", no_world)
    with pytest.raises(trap_link.NoIsolatedWorldError):
        await trap_link.reasons(await page.select("#trap-left"))
    assert await page.eval("window.__touched") == 0

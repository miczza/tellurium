"""The hit check before a press follows the page's scroll (A2 part C, a fix of A1).

``DOM.getNodeForLocation`` takes document coordinates: a viewport point taken as
one lands, once the page scrolled, on "Delete account" at the top of the page.
"""

from __future__ import annotations


async def test_human_click_below_the_fold_reaches_its_target(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/below_fold.html")
    cancel = await tab.select("#cancel")
    await cancel.hover()
    await cancel.click(human=True)
    assert await tab.eval("document.title") == "cancelled"
    assert await tab.eval("scrollY") > 0  # the page did scroll to reach it

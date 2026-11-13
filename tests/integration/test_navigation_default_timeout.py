"""``Tab.get`` without a timeout reads the default navigation deadline at
each call: a slow machine (or the CI, ``tests.timeout_scale``) may stretch it."""

from __future__ import annotations

import pytest

from tellurium import NavigationTimeoutError
from tellurium.browser import navigation


async def test_a_navigation_without_a_timeout_takes_the_default_of_the_moment(
    browser, local_server, monkeypatch
):
    monkeypatch.setattr(navigation, "NAVIGATION_TIMEOUT", 1.0)
    with pytest.raises(NavigationTimeoutError) as caught:
        await browser.main_tab.get(f"{local_server}/slow/5000/x")
    assert caught.value.timeout == 1.0 and caught.value.phase == "commit"


async def test_an_explicit_timeout_wins_over_the_default(browser, local_server, monkeypatch):
    monkeypatch.setattr(navigation, "NAVIGATION_TIMEOUT", 0.5)
    await browser.main_tab.get(f"{local_server}/basic.html", timeout=30)
    assert browser.main_tab.url.endswith("/basic.html")

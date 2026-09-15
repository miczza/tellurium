"""Tab API additions against real Chrome: waits, xpath_all, pdf, window control."""
from __future__ import annotations

import pytest


@pytest.fixture
async def tree(browser, local_server):
    return await browser.new_tab(f"{local_server}/tree.html")


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


async def test_xpath_all_returns_every_match(tree):
    prices = await tree.xpath_all("//p[@class='price']/b")
    assert [await p.text() for p in prices] == ["9.99", "19.99"]


async def test_xpath_all_is_empty_when_nothing_matches(tree):
    assert await tree.xpath_all("//table") == []


async def test_select_all_waits_for_late_elements(tree):
    found = await tree.select_all("#late", timeout=5)
    assert len(found) == 1
    assert await found[0].text() == "Here at last"


async def test_select_all_without_timeout_does_not_wait(tree):
    assert await tree.select_all("#late") == []


async def test_find_all_waits_for_late_text(tree):
    found = await tree.find_all("Here at last", timeout=5)
    assert found and await found[0].text() == "Here at last"


# ---------------------------------------------------------------------------
# wait_for states
# ---------------------------------------------------------------------------


async def test_wait_for_visible(tree):
    element = await tree.wait_for("#late", timeout=5)
    assert await element.text() == "Here at last"


async def test_wait_for_attached_matches_a_hidden_element(tree):
    element = await tree.wait_for("#hidden-note", state="attached", timeout=5)
    assert await element.attr("id") == "hidden-note"


async def test_wait_for_hidden_on_a_display_none_element(tree):
    assert await tree.wait_for("#hidden-note", state="hidden", timeout=5) is None


async def test_wait_for_visible_times_out_on_a_hidden_element(tree):
    with pytest.raises(TimeoutError):
        await tree.wait_for("#hidden-note", state="visible", timeout=1)


async def test_wait_for_detached(tree):
    assert await tree.wait_for("#doomed", state="detached", timeout=5) is None
    assert await tree.select_all("#doomed") == []


# ---------------------------------------------------------------------------
# wait_for_url globbing
# ---------------------------------------------------------------------------


async def test_wait_for_url_matches_a_glob(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    await tab.wait_for_url("*/basic.html", timeout=5)


async def test_wait_for_url_still_matches_a_substring(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    await tab.wait_for_url("basic", timeout=5)


async def test_wait_for_url_glob_is_anchored(browser, local_server):
    """"basic.html" as a glob must not match the full URL by accident."""
    tab = await browser.new_tab(f"{local_server}/basic.html")
    with pytest.raises(TimeoutError):
        await tab.wait_for_url("basic.htm?", timeout=1)


# ---------------------------------------------------------------------------
# pdf / screenshot
# ---------------------------------------------------------------------------


async def test_pdf_returns_a_pdf(browser, local_server, tmp_path):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    out = tmp_path / "page.pdf"
    data = await tab.pdf(str(out))
    assert data.startswith(b"%PDF")
    assert out.read_bytes() == data


async def test_pdf_accepts_print_options(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    portrait = await tab.pdf()
    landscape = await tab.pdf(landscape=True)
    assert landscape.startswith(b"%PDF")
    assert landscape != portrait


async def test_screenshot_jpeg_quality_changes_the_size(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/dashboard.html")
    low = await tab.screenshot(format="jpeg", quality=10)
    high = await tab.screenshot(format="jpeg", quality=95)
    assert low.startswith(b"\xff\xd8")
    assert len(low) < len(high)


# ---------------------------------------------------------------------------
# Window control
# ---------------------------------------------------------------------------


async def test_bring_to_front(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    await tab.bring_to_front()
    assert await tab.eval("document.visibilityState") == "visible"


async def test_set_viewport_resizes_the_window(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    await tab.set_viewport(900, 700)
    width = await tab.eval("window.innerWidth")
    assert 0 < width <= 900


async def test_maximize_and_minimize_do_not_raise(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    await tab.maximize()
    await tab.minimize()


async def test_viewport_launch_flag_sizes_the_window(local_server):
    from tellurium import Browser

    browser = await Browser.launch(headless=True, viewport=(1024, 768))
    async with browser:
        tab = await browser.new_tab(f"{local_server}/basic.html")
        assert await tab.eval("window.innerWidth") == 1024


async def test_mouse_profile_is_wired_through_launch(local_server):
    from tellurium import Browser

    browser = await Browser.launch(headless=True, mouse_profile="hasty")
    async with browser:
        tab = await browser.new_tab(f"{local_server}/basic.html")
        assert tab._mouse_profile == "hasty"
        await tab.mouse_move(120, 120, human=True)


async def test_manual_timezone_override_without_stealth(local_server):
    from tellurium import Browser

    browser = await Browser.launch(headless=True, timezone="Asia/Tokyo")
    async with browser:
        tab = browser.main_tab
        await tab.get(f"{local_server}/basic.html")
        zone = await tab.eval(
            "Intl.DateTimeFormat().resolvedOptions().timeZone"
        )
        assert zone == "Asia/Tokyo"


async def test_manual_languages_override_without_stealth(local_server):
    from tellurium import Browser

    browser = await Browser.launch(headless=True, languages=["it-IT", "it", "en"])
    async with browser:
        tab = await browser.new_tab(f"{local_server}/basic.html")
        assert await tab.eval("Array.from(navigator.languages)") == ["it-IT", "it", "en"]


async def test_manual_overrides_win_over_the_stealth_profile(local_server):
    from tellurium import Browser

    browser = await Browser.launch(
        headless=True, stealth=True, seed=1,
        timezone="Europe/Rome", languages=["it-IT", "it"],
    )
    async with browser:
        tab = await browser.new_tab(f"{local_server}/basic.html")
        assert await tab.eval(
            "Intl.DateTimeFormat().resolvedOptions().timeZone"
        ) == "Europe/Rome"
        assert await tab.eval("Array.from(navigator.languages)") == ["it-IT", "it"]

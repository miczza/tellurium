"""Tab.keyboard_press: keys the page acts on (P1). Enter submits, Tab moves the
focus, arrows move a <select>, Control+a selects all; an unknown key sends nothing."""

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def page(browser, local_server):
    tab = await browser.get(local_server + "/keyboard.html")
    await tab.eval("document.getElementById('first').focus()")
    return tab


async def test_enter_submits_the_focused_form(page):
    await page.keyboard_press("Enter")
    assert await page.eval("window.submits") == 1


async def test_tab_moves_the_focus(page):
    await page.keyboard_press("Tab")
    assert await page.eval("document.activeElement.id") == "second"
    await page.keyboard_press("Shift+Tab")
    assert await page.eval("document.activeElement.id") == "first"


async def test_arrow_down_changes_the_select(page):
    await page.eval("document.getElementById('role').focus()")
    await page.keyboard_press("ArrowDown")
    assert await page.eval("document.getElementById('role').value") == "admin"


async def test_control_a_then_backspace_empties_the_field(page):
    await page.keyboard_press("Control+a")
    await page.keyboard_press("Backspace")
    assert await page.eval("document.getElementById('first').value") == ""


async def test_a_printable_key_types_its_text(page):
    await page.eval("document.getElementById('second').focus()")
    await page.keyboard_press("x", human=True)
    await page.keyboard_press("Space")
    await page.keyboard_press("7")
    assert await page.eval("document.getElementById('second').value") == "x 7"


@pytest.mark.parametrize("combo", ["Entr", "Hyper+a"])
async def test_an_unknown_key_sends_no_event(page, combo):
    with pytest.raises(ValueError):
        await page.keyboard_press(combo)
    assert await page.eval("window.keydowns") == 0
    assert await page.eval("window.submits") == 0

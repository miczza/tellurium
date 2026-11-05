"""Tab.keyboard_press: keys the page acts on (P1). Enter submits, Tab moves the
focus, arrows move a <select>, Control+a/c/v/x/z edit as on Linux on every system;
an unknown key sends nothing."""

import sys

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


@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="on macOS ArrowDown opens a <select>'s popup menu (Chrome's Mac theme "
    "pops the menu on arrow keys), it does not change the value",
)
async def test_arrow_down_changes_the_select(page):
    await page.eval("document.getElementById('role').focus()")
    await page.keyboard_press("ArrowDown")
    assert await page.eval("document.getElementById('role').value") == "admin"


async def test_control_a_then_backspace_empties_the_field(page):
    await page.keyboard_press("Control+a")
    await page.keyboard_press("Backspace")
    assert await page.eval("document.getElementById('first').value") == ""


async def test_control_x_v_and_z_cut_paste_and_undo(page):
    await page.bring_to_front()  # Chrome cuts and copies only in a focused page
    value = "document.getElementById('first').value"
    await page.keyboard_press("Control+a")
    await page.keyboard_press("Control+x")
    assert await page.eval(value) == ""
    await page.keyboard_press("Control+v")
    assert await page.eval(value) == "hello world"
    await page.keyboard_press("Control+z")
    assert await page.eval(value) == ""


async def test_control_c_copies_the_selection(page):
    await page.bring_to_front()
    await page.keyboard_press("Control+a")
    await page.keyboard_press("Control+c")
    await page.eval("document.getElementById('second').focus()")
    await page.keyboard_press("Control+v")
    assert await page.eval("document.getElementById('second').value") == "hello world"


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


@pytest.mark.parametrize("human", [False, True])
async def test_keyboard_type_types_the_exact_text(page, human):
    await page.eval("document.getElementById('second').focus()")
    options = {"human": True, "wpm": 3000, "typos": True} if human else {}
    await page.keyboard_type("Hello, World! 42", **options)
    assert await page.eval("document.getElementById('second').value") == "Hello, World! 42"


async def test_shift_and_a_letter_types_the_capital(page):
    await page.eval("document.getElementById('second').focus()")
    await page.keyboard_press("Shift+a")
    await page.keyboard_press("Shift++")
    assert await page.eval("document.getElementById('second').value") == "A+"


async def test_shift_and_a_digit_or_symbol_types_the_us_layout_character(page):
    await page.eval(
        """(() => {
            const field = document.getElementById('second');
            window.seen = [];
            field.addEventListener('keydown', (e) =>
                window.seen.push([e.key, e.code, e.keyCode, e.shiftKey]));
            field.focus();
        })()"""
    )
    for combo in ("Shift+1", "Shift+/", "Shift+2", "!", "1"):
        await page.keyboard_press(combo)
    assert await page.eval("document.getElementById('second').value") == "!?@!1"
    assert await page.eval("window.seen") == [
        ["!", "Digit1", 49, True],
        ["?", "Slash", 191, True],
        ["@", "Digit2", 50, True],
        ["!", "Digit1", 49, True],  # alone, a shifted symbol is pressed with Shift too
        ["1", "Digit1", 49, False],
    ]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("human", [False, True])
async def test_a_newline_is_enter_in_a_textarea(page, human, newline):
    await page.eval("document.getElementById('notes').focus()")
    await page.keyboard_type(f"a{newline}b", **({"human": True, "wpm": 3000} if human else {}))
    assert await page.eval("document.getElementById('notes').value") == "a\nb"
    assert await page.eval("window.submits") == 0

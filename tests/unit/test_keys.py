"""The shared key table: the codes and text Chrome needs to act on a key press."""

import pytest

from tellurium.browser import keys


def test_named_keys_carry_virtual_key_code_and_text():
    assert keys.parse("Enter") == ("Enter", 0, 13, "\r")
    assert keys.parse("Tab") == ("Tab", 0, 9, "")
    assert keys.parse("ArrowDown").code == 40
    assert keys.parse("F5").code == 116
    assert keys.parse("Space") == (" ", 0, 32, " ")


def test_modifiers_and_printable_keys():
    assert keys.parse("Control+a") == ("a", 2, 65, "a")
    assert keys.parse("Shift+Tab") == ("Tab", 8, 9, "")
    assert keys.parse("ctrl+Shift+z").modifiers == 2 | 8
    assert keys.parse("Meta+c").modifiers == 4
    assert keys.parse("7") == ("7", 0, 55, "7")
    assert keys.parse(";").code == 186
    assert keys.parse("+") == ("+", 8, 187, "+")  # Shift held, as on a keyboard


@pytest.mark.parametrize("combo", ["Entr", "NotAKey", "", "ab"])
def test_unknown_key_is_a_value_error(combo):
    with pytest.raises(ValueError, match="Unknown key"):
        keys.parse(combo)


def test_unknown_modifier_is_a_value_error():
    with pytest.raises(ValueError, match="Unknown modifier 'Hyper'"):
        keys.parse("Hyper+a")


async def _sent(combo, **kwargs):
    sent = []

    async def send(method, params):
        sent.append((method, params))
        return {}

    await keys.press(send, combo, **kwargs)
    assert {m for m, _ in sent} == {"Input.dispatchKeyEvent"}
    return [p for _, p in sent]


async def test_press_sends_raw_key_down_char_and_key_up():
    events = await _sent("Enter")
    assert [e["type"] for e in events] == ["rawKeyDown", "char", "keyUp"]
    assert all(e["windowsVirtualKeyCode"] == 13 and e["key"] == "Enter" for e in events)
    assert events[1]["text"] == "\r"


async def test_a_key_without_text_sends_no_char():
    events = await _sent("ArrowDown")
    assert [e["type"] for e in events] == ["rawKeyDown", "keyUp"]


async def test_control_and_meta_shortcuts_type_nothing():
    for combo in ("Control+a", "Meta+a"):
        events = await _sent(combo)
        assert [e["type"] for e in events] == ["rawKeyDown", "keyUp"]
        assert all("text" not in e for e in events)


async def test_unknown_key_sends_nothing():
    sent = []

    async def send(method, params):
        sent.append(method)

    with pytest.raises(ValueError):
        await keys.press(send, "Entr")
    assert sent == []


async def test_human_press_dwells_between_down_and_up(monkeypatch):
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(keys.asyncio, "sleep", sleep)
    await _sent("a", human=True)
    assert len(slept) == 1 and 0.04 <= slept[0] <= 0.11
    slept.clear()
    await _sent("a")
    assert slept == []


def test_typing_events_of_a_letter_carry_its_codes():
    assert keys.typing_event("a", "rawKeyDown") == {
        "type": "rawKeyDown",
        "key": "a",
        "code": "KeyA",
        "windowsVirtualKeyCode": 65,
    }
    assert keys.typing_event("a", "char") == {"type": "char", "text": "a", "key": "a"}
    assert keys.typing_event("A", "keyUp") == {
        "type": "keyUp",
        "key": "A",
        "code": "KeyA",
        "windowsVirtualKeyCode": 65,
    }


def test_typing_events_of_other_characters_put_the_text_on_key_down():
    assert keys.typing_event("1", "rawKeyDown") == {"type": "keyDown", "key": "1", "text": "1"}
    assert keys.typing_event("1", "char") is None
    assert keys.typing_event("1", "keyUp") == {"type": "keyUp", "key": "1"}
    assert keys.plain_events("!") == [
        {"type": "keyDown", "key": "!", "text": "!"},
        {"type": "keyUp", "key": "!"},
    ]


def test_typing_events_of_a_named_key_carry_no_text():
    down = keys.typing_event("Backspace", "rawKeyDown")
    assert down["type"] == "keyDown" and down["windowsVirtualKeyCode"] == 8
    assert down["code"] == "Backspace" and "text" not in down
    assert keys.typing_event("Backspace", "char") is None
    assert keys.typing_event("Backspace", "keyUp")["type"] == "keyUp"


def test_plus_is_a_key_after_modifiers_too():
    assert keys.parse("Control++") == ("+", 2 | 8, 187, "+")
    assert keys.parse("Control+Shift++").modifiers == 2 | 8
    with pytest.raises(ValueError, match="Unknown key"):
        keys.parse("Control+")


def test_shift_and_a_letter_is_the_capital_letter():
    assert keys.parse("Shift+a") == ("A", 8, 65, "A")
    assert keys.parse("Shift+A") == ("A", 8, 65, "A")


@pytest.mark.parametrize(
    ("combo", "expected"),
    [
        ("Shift+1", ("!", 8, 49, "!")),
        ("Shift+2", ("@", 8, 50, "@")),
        ("Shift+0", (")", 8, 48, ")")),
        ("Shift+/", ("?", 8, 191, "?")),
        ("Shift+=", ("+", 8, 187, "+")),
        ("Shift+`", ("~", 8, 192, "~")),
        ("Shift+'", ('"', 8, 222, '"')),
        ("Shift+\\", ("|", 8, 220, "|")),
        ("Shift++", ("+", 8, 187, "+")),  # already the shifted character
    ],
)
def test_shift_and_a_digit_or_symbol_is_the_us_layout_character(combo, expected):
    assert keys.parse(combo) == expected


def test_a_shifted_character_alone_is_pressed_with_shift_on_its_physical_key():
    assert keys.parse("!") == ("!", 8, 49, "!")
    assert keys.parse("?") == ("?", 8, 191, "?")
    assert keys.parse("Alt+@") == ("@", 1 | 8, 50, "@")
    assert keys.parse("1") == ("1", 0, 49, "1")  # an unshifted one: no Shift
    assert keys.parse("A").modifiers == 0  # a letter keeps its modifiers: Control+A stays


@pytest.mark.parametrize(
    ("combo", "code"),
    [
        ("Shift+1", "Digit1"),
        ("!", "Digit1"),
        ("Shift+/", "Slash"),
        ("a", "KeyA"),
        ("Shift+a", "KeyA"),
        ("Enter", "Enter"),
        ("Space", "Space"),
        ("ArrowDown", "ArrowDown"),
        (";", "Semicolon"),
    ],
)
async def test_every_event_carries_the_dom_code_of_the_physical_key(combo, code):
    events = await _sent(combo)
    assert all(e["code"] == code for e in events)


async def test_shift_and_a_digit_types_its_shifted_text_with_the_digit_key():
    events = await _sent("Shift+1")
    assert [e["type"] for e in events] == ["rawKeyDown", "char", "keyUp"]
    assert all(e["key"] == "!" and e["windowsVirtualKeyCode"] == 49 for e in events)
    assert all(e["modifiers"] == 8 for e in events)
    assert events[1]["text"] == "!"


def test_a_key_without_a_us_layout_position_has_no_dom_code():
    assert "code" not in keys.event(keys.parse("é"), "keyUp")


def test_a_newline_is_typed_as_enter():
    down, up = keys.plain_events("\n")
    assert down["key"] == "Enter" and down["windowsVirtualKeyCode"] == 13
    assert down["text"] == "\r" and down["type"] == "keyDown"
    assert up["key"] == "Enter" and up["type"] == "keyUp" and "text" not in up
    assert keys.typing_event("\n", "rawKeyDown") == down
    assert keys.typing_event("\n", "char") is None


@pytest.mark.parametrize(
    "combo, command",
    [
        ("Control+a", "selectAll"),
        ("Control+A", "selectAll"),
        ("Control+c", "copy"),
        ("Control+v", "paste"),
        ("Control+x", "cut"),
        ("Control+z", "undo"),
    ],
)
async def test_control_editing_shortcuts_carry_their_command_on_key_down(combo, command):
    """macOS binds editing to Command: without the command, Control+a there
    would select nothing. Sent on every system, so all behave alike."""
    events = await _sent(combo)
    assert events[0]["type"] == "rawKeyDown" and events[0]["commands"] == [command]
    assert all("commands" not in e for e in events[1:])


@pytest.mark.parametrize("combo", ["a", "Control+b", "Control+Shift+z", "Alt+a", "Meta+a"])
async def test_other_keys_carry_no_command(combo):
    assert all("commands" not in e for e in await _sent(combo))

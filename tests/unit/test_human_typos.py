"""Typo simulation (design doc 05 §"Typo Simulation"): opt-in, ~2%/char."""

from __future__ import annotations

import random

from tellurium.stealth.human import (
    BACKSPACE_KEY,
    KEYBOARD_NEIGHBOURS,
    TYPO_RATE,
    HumanTyping,
    adjacent_key,
)


class _Rng:
    """Deterministic stand-in: typo when *hit*, first neighbour as the slip."""

    def __init__(self, hit: bool):
        self._hit = hit

    def random(self) -> float:
        return 0.0 if self._hit else 1.0

    def choice(self, seq):
        return seq[0]


def _keys(events):
    return [e["key"] for e in events if e["type"] == "rawKeyDown"]


def test_typos_are_off_by_default():
    typer = HumanTyping(rng=_Rng(hit=True))
    assert _keys(typer.get_events("hello")) == list("hello")


def test_typo_inserts_wrong_key_backspace_then_the_right_one():
    typer = HumanTyping(typos=True, rng=_Rng(hit=True))
    keys = _keys(typer.get_events("a"))
    wrong = KEYBOARD_NEIGHBOURS["a"][0]
    assert keys == [wrong, BACKSPACE_KEY, "a"]


def test_a_typo_emits_a_full_event_triple_per_key():
    typer = HumanTyping(typos=True, rng=_Rng(hit=True))
    events = typer.get_events("a")
    assert len(events) == 9  # 3 keys x (rawKeyDown, char, keyUp)
    assert [e["type"] for e in events[:3]] == ["rawKeyDown", "char", "keyUp"]


def test_no_typo_when_the_dice_say_no():
    typer = HumanTyping(typos=True, rng=_Rng(hit=False))
    assert _keys(typer.get_events("abc")) == ["a", "b", "c"]


def test_characters_without_neighbours_are_never_mistyped():
    typer = HumanTyping(typos=True, rng=_Rng(hit=True))
    assert _keys(typer.get_events("1")) == ["1"]
    assert adjacent_key("1") is None


def test_case_is_preserved_in_a_slip():
    assert adjacent_key("S", _Rng(hit=True)).isupper()
    assert adjacent_key("s", _Rng(hit=True)).islower()


def test_adjacency_is_symmetric_on_the_qwerty_grid():
    for key, neighbours in KEYBOARD_NEIGHBOURS.items():
        for neighbour in neighbours:
            assert key in KEYBOARD_NEIGHBOURS[neighbour], f"{key}/{neighbour} asymmetric"


def test_typo_rate_is_about_two_percent():
    typer = HumanTyping(typos=True, rng=random.Random(7))
    text = "the quick brown fox jumps over the lazy dog" * 40
    events = typer.get_events(text)
    extra = len(_keys(events)) - len(text)  # 2 extra keys per typo
    rate = (extra / 2) / len(text)
    assert TYPO_RATE == 0.02
    assert 0.005 < rate < 0.045


def test_a_seeded_rng_makes_the_run_reproducible():
    first = _keys(HumanTyping(typos=True, rng=random.Random(11)).get_events("hello world"))
    second = _keys(HumanTyping(typos=True, rng=random.Random(11)).get_events("hello world"))
    assert first == second


def test_corrections_survive_key_rollover():
    from tellurium.stealth.human import apply_key_rollover

    events = HumanTyping(typos=True, rng=_Rng(hit=True)).get_events("ab")
    rolled = apply_key_rollover(events)
    assert _keys(rolled) == _keys(events)

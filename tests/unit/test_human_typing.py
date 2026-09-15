from tellurium.stealth.human import FINGER_MAP, HumanTyping


def test_typing_event_sequence():
    typer = HumanTyping(wpm=52)
    events = typer.get_events("ab")
    types = [e["type"] for e in events]
    assert types == ["rawKeyDown", "char", "keyUp", "rawKeyDown", "char", "keyUp"]


def test_typing_alternate_hands_faster():
    typer = HumanTyping(wpm=52)
    samples_alt = [typer._compute_iki("a", "k") for _ in range(200)]
    samples_same = [typer._compute_iki("d", "e") for _ in range(200)]
    avg_alt = sum(samples_alt) / len(samples_alt)
    avg_same = sum(samples_same) / len(samples_same)
    assert avg_alt < avg_same  # alternate hands should be faster


def test_dwell_time_distribution():
    typer = HumanTyping()
    dwells = [typer._compute_dwell("a") for _ in range(1000)]
    avg = sum(dwells) / len(dwells)
    assert 80 < avg < 160  # centered around 116ms


def test_finger_map_coverage():
    assert "a" in FINGER_MAP
    assert " " in FINGER_MAP
    assert "z" in FINGER_MAP


def test_typing_single_char():
    typer = HumanTyping()
    events = typer.get_events("x")
    assert len(events) == 3
    assert events[0]["type"] == "rawKeyDown"
    assert events[1]["type"] == "char"
    assert events[2]["type"] == "keyUp"


def test_typing_empty_string():
    typer = HumanTyping()
    events = typer.get_events("")
    assert events == []

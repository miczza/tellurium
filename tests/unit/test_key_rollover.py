"""Tests for apply_key_rollover — fast-typist flight-time overlap."""

from tellurium.stealth.human import apply_key_rollover


def _make_events(chars_with_iki: list[tuple[str, float, float]]) -> list[dict]:
    """Build a (rawKeyDown, char, keyUp) triple per char, with given iki and dwell."""
    events = []
    for ch, iki, dwell in chars_with_iki:
        events.append({"type": "rawKeyDown", "key": ch, "delay_ms": iki})
        events.append({"type": "char", "key": ch, "delay_ms": 2.0})
        events.append({"type": "keyUp", "key": ch, "delay_ms": dwell})
    return events


def test_rollover_no_overlap_for_slow_typing():
    """IKI > 80ms → no reordering, same event sequence."""
    events = _make_events([("a", 200.0, 116.0), ("b", 200.0, 116.0)])
    rolled = apply_key_rollover(events, threshold_ms=80.0)
    assert [e["type"] for e in rolled] == [
        "rawKeyDown",
        "char",
        "keyUp",
        "rawKeyDown",
        "char",
        "keyUp",
    ]
    assert [e["key"] for e in rolled] == ["a", "a", "a", "b", "b", "b"]


def test_rollover_overlap_for_fast_typing():
    """IKI < threshold between chars N and N+1 → rawKeyDown[N+1] before keyUp[N].

    Input sequence (per-char: down, char, up):
        A_down  A_char  A_up(dwell=116)  B_down(iki=40)  B_char  B_up
    With rollover + threshold=80, B_down overtakes A_up:
        A_down  A_char  B_down  A_up     B_char  B_up
    """
    events = _make_events([("a", 150.0, 116.0), ("b", 40.0, 116.0)])
    rolled = apply_key_rollover(events, threshold_ms=80.0)

    seq = [(e["type"], e["key"]) for e in rolled]
    # B's rawKeyDown comes before A's keyUp
    b_down_idx = seq.index(("rawKeyDown", "b"))
    a_up_idx = seq.index(("keyUp", "a"))
    assert b_down_idx < a_up_idx, f"Expected B_down before A_up under rollover; got {seq}"


def test_rollover_preserves_per_char_triple_order():
    """Within one char the rawKeyDown → char → keyUp order must never invert."""
    events = _make_events([("x", 200.0, 116.0), ("y", 30.0, 116.0), ("z", 30.0, 116.0)])
    rolled = apply_key_rollover(events, threshold_ms=80.0)

    for key in ("x", "y", "z"):
        indices = {}
        for i, e in enumerate(rolled):
            if e["key"] == key:
                indices[e["type"]] = i
        assert indices["rawKeyDown"] < indices["char"] < indices["keyUp"], (
            f"Per-char ordering broken for {key!r}: {indices}"
        )

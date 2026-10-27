"""``Element.drag_to`` delegates to :mod:`tellurium.browser.drag`."""

from __future__ import annotations

from tellurium.browser import drag
from tellurium.browser.element import Element


async def test_drag_to_delegates_to_the_drag_module(monkeypatch):
    calls = []

    async def fake_drag(source, target, steps):
        calls.append((source, target, steps))

    monkeypatch.setattr(drag, "drag", fake_drag)
    source, target = Element.__new__(Element), Element.__new__(Element)
    await source.drag_to(target, steps=3)
    assert calls == [(source, target, 3)]

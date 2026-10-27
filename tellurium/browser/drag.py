"""Drag one element onto another with real mouse events (``Input.dispatchMouseEvent``)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from tellurium.browser import geometry

if TYPE_CHECKING:
    from tellurium.browser.element import Element


async def drag(source: Element, target: Element, steps: int) -> None:
    """Press on *source*, move in *steps* straight steps to *target*, release there.

    Both ends must be hittable before the press: otherwise
    :class:`~tellurium.browser.geometry.ElementNotHittableError` and no event is sent.
    """
    tab = source._tab
    await source.scroll_into_view()
    sx, sy = await source._center()
    await target.scroll_into_view()
    tx, ty = await target._center()
    await geometry.ensure_hit(target, tx, ty)  # both ends hittable before the press
    await geometry.ensure_hit(source, sx, sy)
    await tab.mouse_move(sx, sy)
    await tab._dispatch_mouse(
        {
            "type": "mousePressed",
            "x": sx,
            "y": sy,
            "button": "left",
            "clickCount": 1,
        }
    )
    for i in range(1, steps + 1):
        frac = i / steps
        mx = sx + (tx - sx) * frac
        my = sy + (ty - sy) * frac
        await tab.mouse_move(mx, my)
        await asyncio.sleep(0.01)
    await tab._dispatch_mouse(
        {
            "type": "mouseReleased",
            "x": tx,
            "y": ty,
            "button": "left",
            "clickCount": 1,
        }
    )

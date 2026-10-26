"""The browser window a tab lives in: its id, its bounds, its state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tellurium.browser.tab import Tab

logger = logging.getLogger("tellurium")


async def window_id(tab: Tab) -> int | None:
    """Resolve (and cache on *tab*) the tab's browser window id, or *None*."""
    if tab._window_id is not None:
        return tab._window_id
    try:
        resp = await tab._browser._router.root.send(
            "Browser.getWindowForTarget",
            {"targetId": tab._target_id},
            timeout=5.0,
        )
    except Exception:  # noqa: BLE001 — not implemented on every target type
        return None
    tab._window_id = resp.get("windowId")
    return tab._window_id


async def set_window_bounds(tab: Tab, bounds: dict) -> bool:
    """Send ``Browser.setWindowBounds``; return False when unavailable."""
    wid = await window_id(tab)
    if wid is None:
        return False
    try:
        await tab._browser._router.root.send(
            "Browser.setWindowBounds",
            {
                "windowId": wid,
                "bounds": bounds,
            },
            timeout=5.0,
        )
    except Exception:  # noqa: BLE001 — degrade, never break the caller
        return False
    # Window geometry changed → the cached screenX/screenY offset is stale.
    tab._screen_offset = None
    return True


async def set_viewport(tab: Tab, width: int, height: int) -> None:
    """Resize the browser window to *width* x *height*.

    Resizing is done with ``Browser.setWindowBounds``, which moves the real
    window — every JS-visible metric (``innerWidth``, ``outerWidth``,
    ``screenX``…) stays self-consistent.  ``--window-size`` cannot be
    changed after launch, so it is not an option here.

    Fallback: if ``Browser.setWindowBounds`` is unavailable (older
    headless shells, non-top-level targets) the call degrades to
    ``Emulation.setDeviceMetricsOverride`` and logs a warning — that
    command is itself a detection signal (it desynchronises
    ``window.outerWidth``/``screen`` from the emulated viewport), so
    prefer ``Browser.launch(viewport=(w, h))`` when stealth matters.
    """
    if await set_window_bounds(
        tab,
        {
            "width": int(width),
            "height": int(height),
            "windowState": "normal",
        },
    ):
        return
    logger.warning(
        "Browser.setWindowBounds unavailable; falling back to "
        "Emulation.setDeviceMetricsOverride, which is a detectable "
        "fingerprint signal. Prefer Browser.launch(viewport=(%d, %d)).",
        int(width),
        int(height),
    )
    await tab._session.send(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": int(width),
            "height": int(height),
            "deviceScaleFactor": 0,
            "mobile": False,
        },
    )


async def maximize(tab: Tab) -> None:
    """Maximize the browser window (no-op when unavailable)."""
    await set_window_bounds(tab, {"windowState": "maximized"})


async def minimize(tab: Tab) -> None:
    """Minimize the browser window (no-op when unavailable)."""
    await set_window_bounds(tab, {"windowState": "minimized"})


async def bring_to_front(tab: Tab) -> None:
    """Focus the tab / bring its window to the foreground."""
    await tab._session.send("Page.bringToFront", {})

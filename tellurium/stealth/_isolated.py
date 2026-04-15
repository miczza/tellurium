"""Per-frame Isolated World context for human-sim DOM queries.

Rationale: a hostile page can monkey-patch document.querySelector,
Element.prototype.getBoundingClientRect or EventTarget.prototype.addEventListener
to flag automation. Running our DOM queries inside Page.createIsolatedWorld
gives us a fresh document proxy + prototype chain that the page JS cannot
reach, while still seeing the live DOM tree.

Event dispatch (Input.dispatch*) does not need the isolated world — it
bypasses JS entirely and produces isTrusted=true native events.
"""
from __future__ import annotations

_HSIM_WORLD_NAME = "__tellurium_hsim__"


async def get_hsim_world(tab, *, frame_id: str) -> int | None:
    """Return the executionContextId of the human-sim isolated world for frame_id.

    Lazily creates via Page.createIsolatedWorld on first access, caches on
    tab._hsim_worlds. Returns None if the CDP call fails (caller falls back
    to the main world).
    """
    cache: dict[str, int] = tab._hsim_worlds
    cached = cache.get(frame_id)
    if cached is not None:
        return cached

    try:
        resp = await tab._session.send("Page.createIsolatedWorld", {
            "frameId": frame_id,
            "worldName": _HSIM_WORLD_NAME,
            "grantUniversalAccess": False,
        })
    except Exception:
        return None

    ctx_id = resp.get("executionContextId")
    if ctx_id is None:
        return None
    cache[frame_id] = ctx_id
    return ctx_id

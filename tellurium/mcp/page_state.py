"""Where a tab is now (live URL and title) and whether an action navigated it.

``Tab.url`` / ``Tab.title`` are as of the last ``get()``; a click can move the
page anywhere, so the server asks the page itself. A new document has a new
``performance.timeOrigin``: that, not the URL, tells a navigation from a
``pushState`` or a same-page update.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

_PROBE = "[location.href, document.title, performance.timeOrigin, document.readyState]"

# After an action, a navigation it starts may take a moment to begin.
SETTLE = 0.3
# How long to wait for the new document to become readable after an action.
WAIT = 15.0
POLL = 0.2
READ_TIMEOUT = 5.0


@dataclass(frozen=True)
class PageState:
    url: str
    title: str
    origin: float | None = None  # performance.timeOrigin of the document
    ready: str = ""  # document.readyState


async def read(tab: Any, timeout: float = READ_TIMEOUT) -> PageState:
    """The tab's live URL, title and document identity (one ``eval``)."""
    url, title, origin, ready = await tab.eval(_PROBE, timeout=timeout)
    return PageState(str(url), str(title), float(origin), str(ready))


async def read_or_none(tab: Any, timeout: float = READ_TIMEOUT) -> PageState | None:
    try:
        return await read(tab, timeout)
    except Exception:  # noqa: BLE001 - a page between documents cannot answer
        return None


async def after_action(
    tab: Any,
    before: PageState | None,
    *,
    settle: float = SETTLE,
    wait: float = WAIT,
    poll: float = POLL,
) -> tuple[PageState, bool]:
    """The state once the page settled after an action, and whether it navigated.

    A new document is waited for until it leaves ``loading`` (or *wait* s pass).
    A page that never answers counts as navigated, at the URL ``Tab.url`` knows:
    the agent should look again before acting.
    """
    if settle:
        await asyncio.sleep(settle)
    deadline = asyncio.get_running_loop().time() + wait
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        state = await read_or_none(tab, timeout=max(0.1, min(READ_TIMEOUT, remaining)))
        if state is not None:
            navigated = before is None or state.origin != before.origin
            if not (navigated and state.ready == "loading"):
                return state, navigated
        if asyncio.get_running_loop().time() >= deadline:
            if state is not None:
                return state, True
            return PageState(tab.url, ""), True
        await asyncio.sleep(poll)

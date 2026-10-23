"""Remote-object handles of a tab: grouping, release, stale detection.

Every ``objectId`` the inspector hands out is a strong reference to its JS
value: a DOM node behind one cannot be garbage-collected, even once removed
from the page. A tab therefore resolves every node into its own
``objectGroup`` and releases what it no longer needs:

* an :class:`Element` dropped by Python is released by a finalizer, batched;
* ``Element.release()`` releases one handle at once;
* the whole group is released on each main-frame navigation (the group then
  rotates) and on ``Tab.close()``.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import weakref
from typing import TYPE_CHECKING, Any

from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.element import Element
    from tellurium.browser.tab import Tab
    from tellurium.cdp.transport._session import Session

logger = logging.getLogger("tellurium")

# Release calls are housekeeping: never let one stall the caller for long.
_RELEASE_TIMEOUT = 5.0
# Bound of a command on an element (a page frozen by an open dialog, a hung
# renderer); generous because callFunctionOn awaits the page's promises.
HANDLE_TIMEOUT = 30.0

# Chrome's messages for a node or remote object that no longer exists.
_STALE_MESSAGES = (
    "Cannot find context with specified id",
    "Could not find object with given id",
    "Could not find node with given id",
    "No node with given id found",
    "Node with given id does not belong to the document",
)

_group_ids = itertools.count(1)


class StaleElementError(CDPError):
    """The element is gone: its document navigated away, or it was released."""


def as_stale(error: CDPError) -> CDPError:
    """Return a :class:`StaleElementError` for a vanished node, else *error*."""
    if isinstance(error, StaleElementError):
        return error
    if any(text in error.message for text in _STALE_MESSAGES):
        stale = StaleElementError(
            f"Element is stale (document navigated or node released): {error.message}",
            error.code,
        )
        stale.__cause__ = error
        return stale
    return error


async def send_on_handle(session: Session, method: str, params: dict) -> dict:
    """``session.send`` for a command on an element handle, bounded by ``HANDLE_TIMEOUT``.

    Stale errors are typed; expiry raises the builtin ``TimeoutError``.
    """
    try:
        return await session.send(method, params, timeout=HANDLE_TIMEOUT)
    except CDPError as exc:
        raise as_stale(exc) from exc
    except asyncio.TimeoutError:
        raise TimeoutError(f"{method} got no answer within {HANDLE_TIMEOUT}s") from None


def handles_of(tab: Tab | Any) -> HandleGroup | None:
    """The :class:`HandleGroup` of *tab* (``None`` for test doubles)."""
    handles = getattr(tab, "_handles", None)
    return handles if isinstance(handles, HandleGroup) else None


async def resolve_node(session: Session, tab: Tab | Any, node_id: int, released: bool) -> str:
    """Resolve *node_id* into the tab's object group and return the ``objectId``."""
    if released:
        raise StaleElementError("Element was released")
    params: dict[str, Any] = {"nodeId": node_id}
    if handles := handles_of(tab):
        params["objectGroup"] = handles.name
    result = await send_on_handle(session, "DOM.resolveNode", params)
    return result["object"]["objectId"]


async def elements_from_array(session: Session, tab: Tab, array_object_id: str) -> list[Element]:
    """Map a remote JS array of DOM nodes to :class:`Element`s, then free the array.

    The items inherit the array's object group, so each element keeps its
    node's ``objectId`` without a ``DOM.requestNode`` round trip.
    """
    from tellurium.browser.element import Element

    try:
        props = await send_on_handle(
            session, "Runtime.getProperties", {"objectId": array_object_id, "ownProperties": True}
        )
    finally:
        handles = handles_of(tab)
        if handles is not None:
            handles.discard(array_object_id)
    elements: list[Element] = []
    for prop in props.get("result", []):
        if not prop.get("name", "").isdigit():
            continue
        object_id = prop.get("value", {}).get("objectId")
        if object_id:
            elements.append(Element(session, tab, object_id=object_id))
    return elements


class HandleGroup:
    """Owns the remote objects a tab's queries resolve (one ``objectGroup``)."""

    def __init__(self, session: Session):
        self._session = session
        self._prefix = f"tellurium-{next(_group_ids)}"
        self._generation = 0
        self._orphans: list[tuple[str, str]] = []
        self._tasks: set[asyncio.Task] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    @property
    def name(self) -> str:
        """The ``objectGroup`` new handles go into."""
        return f"{self._prefix}.{self._generation}"

    def adopt(self, element: Element, object_id: str) -> weakref.finalize:
        """Release *object_id* when *element* is garbage-collected."""
        self._loop = self._loop or asyncio.get_running_loop()
        finalizer = weakref.finalize(element, self._orphan, object_id, self.name)
        finalizer.atexit = False
        return finalizer

    def discard(self, object_id: str) -> None:
        """Release *object_id* soon (batched, best effort)."""
        self._loop = self._loop or asyncio.get_running_loop()
        self._orphan(object_id, self.name)

    async def release(self, object_id: str) -> None:
        """Release one handle now (best effort)."""
        await self._send("Runtime.releaseObject", {"objectId": object_id})

    def rotate(self) -> None:
        """Start a new group (main-frame navigation) and release the old one."""
        old = self.name
        self._generation += 1
        self._orphans = [(oid, group) for oid, group in self._orphans if group != old]
        self._spawn(self._send("Runtime.releaseObjectGroup", {"objectGroup": old}))

    async def drain(self) -> None:
        """Wait until every pending release has been sent and answered."""
        await asyncio.sleep(0)  # let finalizer callbacks schedule their flush
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
            await asyncio.sleep(0)

    async def close(self) -> None:
        """Release the current group and stop releasing (``Tab.close()``)."""
        if self._closed:
            return
        self._closed = True
        self._orphans.clear()
        for task in list(self._tasks):
            task.cancel()
        await self._send("Runtime.releaseObjectGroup", {"objectGroup": self.name})

    # ------------------------------------------------------------------

    def _orphan(self, object_id: str, group: str) -> None:
        # A finalizer may run from any thread, or after the loop closed.
        if self._closed or group != self.name or self._loop is None:
            return
        self._orphans.append((object_id, group))
        if len(self._orphans) == 1:
            try:
                self._loop.call_soon_threadsafe(self._schedule_flush)
            except RuntimeError:  # loop closed: the browser is gone anyway
                self._orphans.clear()

    def _schedule_flush(self) -> None:
        self._spawn(self._flush())

    async def _flush(self) -> None:
        batch, self._orphans = self._orphans, []
        current = self.name
        await asyncio.gather(
            *(
                self._send("Runtime.releaseObject", {"objectId": oid})
                for oid, group in batch
                if group == current
            )
        )

    def _spawn(self, coro) -> None:
        if self._closed:
            coro.close()
            return
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send(self, method: str, params: dict) -> None:
        try:
            await self._session.send(method, params, timeout=_RELEASE_TIMEOUT)
        except Exception:  # noqa: BLE001 — the object or the target is already gone
            logger.debug("%s failed", method, exc_info=True)

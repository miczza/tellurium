"""OwnSession — a browser-wide CDP session the relay keeps for itself.

The root session of the pipe belongs to the client, so whatever the relay
must do in Chrome on its own (answer the proxy forwarder's challenge) runs
on a session of its own, opened with ``Target.attachToBrowserTarget``. Its
commands use the relay's ids, like the health probes. :class:`OwnSessions`
keeps them from the client: their replies, their events and the ``Target``
events that name them never reach it, and a client command aimed at one
(its ``sessionId``, or a ``Target.detachFromTarget`` of it by session or by
target id) is refused as Chrome refuses an unknown session.

Chrome announces the new session (``Target.attachedToTarget`` on the root)
*before* it answers ``attachToBrowserTarget``, when its id is not known yet:
while an attach is in flight, whatever would go to the client is held, in
order, and released once the id is known, without that announcement. The
hold lasts one round trip (bounded by the attach's timeout); what is held
counts as queued for the client against the relay's ``HIGH_WATER``, and with
no client nothing is held (it would be dropped all the same).

The detach refused by target id rests on what Chrome does (observed on 156,
pinned by an integration test): ``Target.detachFromTarget`` with the target
id of a browser session detaches that session.

An :class:`OwnSession` has ``send(method, params, timeout)``, ``on`` and
``off``: what :class:`~tellurium.browser.proxy_auth.ProxyAuth` needs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable
from typing import Any, Protocol

logger = logging.getLogger("tellurium")

#: Chrome's code for a command on a session it does not know.
_NO_SESSION = -32001
#: ``Target`` events that name a session in their params.
_NAMING_EVENTS = ("Target.attachedToTarget", "Target.detachedFromTarget")


class CommandError(Exception):
    """Chrome answered one of the relay's own commands with an error."""


class OwnRelay(Protocol):
    """What an :class:`OwnSession` uses of the relay it lives on."""

    own: OwnSessions

    async def call(
        self,
        method: str,
        params: dict | None = None,
        *,
        timeout: float,
        session_id: str | None = None,
    ) -> dict: ...

    def release_held(self) -> None: ...


class OwnSessions:
    """The relay's own sessions on one pipe, and what keeps them from the client."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], None]] = {}  # sessionId -> events
        self._targets: set[str] = set()  # target id of each own session
        self._attaching = 0
        self._held: deque[dict] = deque()
        #: Size of the held messages as they will go to the client (JSON, ASCII).
        self.held_bytes = 0

    @property
    def holding(self) -> bool:
        """Whether messages for the client are held (an attach is in flight)."""
        return self._attaching > 0

    def hold(self, message: dict) -> None:
        self._held.append(message)
        self.held_bytes += len(json.dumps(message, separators=(",", ":"), ensure_ascii=True))

    def begin_attach(self) -> None:
        self._attaching += 1

    def end_attach(self) -> list[dict]:
        """Stop holding (when no other attach is in flight): what may now go to
        the client, in order, without what belongs to an own session."""
        self._attaching -= 1
        if self._attaching:
            return []
        held, self._held = self._held, deque()
        self.held_bytes = 0
        return [m for m in held if "id" in m or not self.take(m)]

    def adopt(self, session_id: str, handler: Callable[[dict], None]) -> None:
        """Keep *session_id* from the client; its events go to *handler*."""
        self._handlers[session_id] = handler

    def adopt_target(self, target_id: str) -> None:
        self._targets.add(target_id)

    def take(self, event: dict) -> bool:
        """Whether *event* belongs to an own session: then it went to that
        session's handler, or is dropped, and must not reach the client."""
        if not self._handlers:
            return False
        handler = self._handlers.get(_field(event, "sessionId"))
        if handler is not None:
            handler(event)
            return True
        params = event.get("params")
        return (
            event.get("method") in _NAMING_EVENTS
            and isinstance(params, dict)
            and _field(params, "sessionId") in self._handlers
        )

    def refusal(self, command: dict) -> dict | None:
        """Chrome's error for a client *command* aimed at an own session, or None."""
        if not self._handlers:
            return None
        params = command.get("params")
        params = params if isinstance(params, dict) else {}
        aimed = _field(command, "sessionId") in self._handlers or (
            command.get("method") == "Target.detachFromTarget"
            and (
                _field(params, "sessionId") in self._handlers
                or _field(params, "targetId") in self._targets
            )
        )
        if not aimed:
            return None
        error = {"code": _NO_SESSION, "message": "Session with given id not found."}
        return {"id": command["id"], "error": error}


class OwnSession:
    """The relay's own browser session; open one with :meth:`attach`."""

    def __init__(self, relay: OwnRelay, session_id: str) -> None:
        self._relay = relay
        self.id = session_id
        self._handlers: dict[str, list[Callable[[dict], Any]]] = {}

    def __repr__(self) -> str:
        return f"<OwnSession {self.id[:8]}…>"

    @classmethod
    async def attach(cls, relay: OwnRelay, timeout: float) -> OwnSession:
        """Attach to the browser target on *relay*'s pipe: its two commands
        within *timeout* seconds in all.

        Raises :class:`TimeoutError`, :class:`~tellurium.multiplexer.relay.RelayClosed`
        or :class:`CommandError`. Messages for the client are held meanwhile.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        own = relay.own
        own.begin_attach()
        try:
            result = await relay.call("Target.attachToBrowserTarget", timeout=timeout)
            session_id = result.get("sessionId")
            if not isinstance(session_id, str) or not session_id:
                raise CommandError("Target.attachToBrowserTarget: no sessionId in the reply")
            session = cls(relay, session_id)
            own.adopt(session_id, session._dispatch)
        finally:
            relay.release_held()
        # Its target id (one per browser session, listed nowhere else) is refused
        # to the client's Target.detachFromTarget too.
        left = deadline - loop.time()
        if left <= 0:
            raise TimeoutError(f"Chrome did not answer within {timeout:g} s")
        info = await session.send("Target.getTargetInfo", timeout=left)
        target_id = (info.get("targetInfo") or {}).get("targetId")
        if not isinstance(target_id, str) or not target_id:
            raise CommandError("Target.getTargetInfo: no targetId in the reply")
        own.adopt_target(target_id)
        return session

    async def send(self, method: str, params: dict | None = None, timeout: float = 10.0) -> dict:
        """*method* on this session: its ``result`` within *timeout* seconds."""
        return await self._relay.call(method, params, timeout=timeout, session_id=self.id)

    def on(self, event: str, handler: Callable[[dict], Any]) -> None:
        """Call *handler* with the ``params`` of each *event* on this session."""
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler: Callable[[dict], Any]) -> None:
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    def _dispatch(self, message: dict) -> None:
        params = message.get("params")
        for handler in list(self._handlers.get(message.get("method", ""), ())):
            try:
                handler(params if isinstance(params, dict) else {})
            except Exception:  # noqa: BLE001 - one bad handler must not stop the relay
                logger.exception("OwnSession: a handler of %s failed", message.get("method"))


def _field(fields: dict, name: str) -> str:
    """The string *name* of *fields*, or "" (also when it is not a string)."""
    value = fields.get(name)
    return value if isinstance(value, str) else ""

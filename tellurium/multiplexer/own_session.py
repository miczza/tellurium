"""OwnSession — a browser-wide CDP session the relay keeps for itself.

The root session of the pipe belongs to the client, so whatever the relay
must do in Chrome on its own (answer the proxy forwarder's challenge) runs
on a session of its own, opened with ``Target.attachToBrowserTarget``. Its
commands use the relay's ids, like the health probes; its replies, its
events and the ``Target`` events that name it never reach the client, and a
client command aimed at it is refused (see :class:`~tellurium.multiplexer.relay.Relay`).

It has ``send(method, params, timeout)``, ``on`` and ``off``: what
:class:`~tellurium.browser.proxy_auth.ProxyAuth` needs of a session.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from tellurium.multiplexer.relay import CommandError

logger = logging.getLogger("tellurium")


class OwnSession:
    """The relay's own browser session; open one with :meth:`attach`."""

    def __init__(self, relay: Any, session_id: str) -> None:
        self._relay = relay
        self.id = session_id
        self._handlers: dict[str, list[Callable[[dict], Any]]] = {}

    def __repr__(self) -> str:
        return f"<OwnSession {self.id[:8]}…>"

    @classmethod
    async def attach(cls, relay: Any, timeout: float) -> OwnSession:
        """Attach to the browser target on *relay*'s pipe within *timeout* seconds.

        Raises :class:`TimeoutError`, :class:`~tellurium.multiplexer.relay.RelayClosed`
        or :class:`~tellurium.multiplexer.relay.CommandError`.
        """
        result = await relay.call("Target.attachToBrowserTarget", timeout=timeout)
        session_id = result.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise CommandError("Target.attachToBrowserTarget: no sessionId in the reply")
        session = cls(relay, session_id)
        relay.adopt(session_id, session._dispatch)
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

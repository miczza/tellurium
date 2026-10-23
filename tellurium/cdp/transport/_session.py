"""CDP session multiplexer over a single transport."""

from __future__ import annotations

import asyncio
import json
import logging

from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.types import CDPError

logger = logging.getLogger(__name__)


class Session:
    """A CDP session targeting a specific browser target."""

    def __init__(self, router: SessionRouter, session_id: str | None):
        self._router = router
        self._session_id = session_id
        self._pending: dict[int, asyncio.Future] = {}
        self._event_handlers: dict[str, list[callable]] = {}
        self._lock = asyncio.Lock()
        self._closed_reason: str | None = None

    async def send(
        self,
        method: str,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        if method in self._router._FORBIDDEN_METHODS:
            raise RuntimeError(
                f"{method} is forbidden — it exposes CDP via Inspector "
                f"and enables Proxy ownKeys trap detection. "
                f"Use Page.createIsolatedWorld + Runtime.evaluate instead."
            )
        if self._closed_reason is not None:
            raise ConnectionError(self._closed_reason)
        msg_id = await self._router._allocate_id()
        async with self._lock:
            msg: dict = {"id": msg_id, "method": method, "params": params or {}}
            if self._session_id is not None:
                msg["sessionId"] = self._session_id
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            self._pending[msg_id] = future
            await self._router._transport.send(json.dumps(msg).encode() + b"\0")
        try:
            if timeout is None:
                return await future
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            # asyncio.wait_for cancels its internal waiter but leaves the
            # future pending. Remove msg_id from _pending so a late reply
            # from Chrome lands on a removed entry in _handle_message
            # (pop returns None, future.set_result is never called).
            # If the reply races the timeout, set_result may still fire
            # on the now-orphan future — benign: no awaiter, no leak.
            self._pending.pop(msg_id, None)
            raise

    def on(self, event_name: str, handler: callable) -> None:
        self._event_handlers.setdefault(event_name, []).append(handler)

    def off(self, event_name: str, handler: callable) -> None:
        handlers = self._event_handlers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)

    async def _handle_message(self, msg: dict) -> None:
        if "id" in msg:
            future = self._pending.pop(msg["id"], None)
            if future and not future.done():
                if "error" in msg:
                    future.set_exception(
                        CDPError(msg["error"]["message"], msg["error"].get("code"))
                    )
                else:
                    future.set_result(msg.get("result", {}))
        elif "method" in msg:
            # Copy: a handler may call off() on itself while we iterate.
            for handler in list(self._event_handlers.get(msg["method"], [])):
                try:
                    handler(msg.get("params", {}))
                except Exception:
                    # A buggy handler must not kill the dispatch loop: every
                    # pending send() would then wait forever.
                    logger.exception("CDP event handler for %s failed", msg["method"])

    def _close(self, reason: str) -> None:
        """Fail every pending command and reject future ones."""
        self._closed_reason = reason
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError(reason))
        self._pending.clear()


class SessionRouter:
    """Multiplexer: one pipe transport -> N sessions."""

    _FORBIDDEN_METHODS: frozenset[str] = frozenset({"Runtime.enable"})

    def __init__(self, transport: CDPTransport):
        self._transport = transport
        self._next_msg_id = 0
        self._id_lock = asyncio.Lock()
        self._sessions: dict[str | None, Session] = {}
        self._root = Session(self, session_id=None)
        self._sessions[None] = self._root

    async def _allocate_id(self) -> int:
        async with self._id_lock:
            self._next_msg_id += 1
            return self._next_msg_id

    @property
    def root(self) -> Session:
        return self._root

    def get_session(self, session_id: str | None) -> Session:
        return self._sessions.get(session_id, self._root)

    def register(self, session_id: str) -> Session:
        """Return the session for an auto-attached *session_id*, creating it."""
        session = self._sessions.get(session_id)
        if session is None:
            session = Session(self, session_id=session_id)
            self._sessions[session_id] = session
        return session

    async def attach(self, target_id: str) -> Session:
        result = await self._root.send(
            "Target.attachToTarget", {"targetId": target_id, "flatten": True}
        )
        sid = result["sessionId"]
        session = Session(self, session_id=sid)
        self._sessions[sid] = session
        return session

    async def detach(self, session: Session) -> None:
        if session._session_id:
            await self._root.send("Target.detachFromTarget", {"sessionId": session._session_id})
            self._sessions.pop(session._session_id, None)

    async def run(self) -> None:
        try:
            while True:
                msg = await self._transport.recv()
                sid = msg.get("sessionId")
                target = self._sessions.get(sid, self._root)
                await target._handle_message(msg)
                if msg.get("method") == "Target.detachedFromTarget":
                    self._drop_session(msg.get("params", {}).get("sessionId"))
        except (ConnectionError, EOFError):
            pass
        finally:
            # Whatever ended the loop (pipe closed, malformed message,
            # cancellation), no reply will ever arrive for pending commands.
            for session in self._sessions.values():
                session._close("Browser pipe closed")

    def _drop_session(self, session_id: str | None) -> None:
        if session_id is None:
            return
        session = self._sessions.pop(session_id, None)
        if session is not None:
            session._close(f"Target detached (session {session_id})")

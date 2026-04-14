"""CDP session multiplexer over a single transport."""
from __future__ import annotations
import asyncio
import json
from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.types import CDPError


class Session:
    """A CDP session targeting a specific browser target."""

    def __init__(self, router: SessionRouter, session_id: str | None):
        self._router = router
        self._session_id = session_id
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._event_handlers: dict[str, list[callable]] = {}
        self._lock = asyncio.Lock()

    async def send(self, method: str, params: dict | None = None) -> dict:
        async with self._lock:
            self._request_id += 1
            msg_id = self._request_id
            msg: dict = {"id": msg_id, "method": method, "params": params or {}}
            if self._session_id is not None:
                msg["sessionId"] = self._session_id
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            self._pending[msg_id] = future
            await self._router._transport.send(json.dumps(msg).encode() + b"\0")
        return await future

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
            for handler in self._event_handlers.get(msg["method"], []):
                handler(msg.get("params", {}))


class SessionRouter:
    """Multiplexer: one pipe transport -> N sessions."""

    def __init__(self, transport: CDPTransport):
        self._transport = transport
        self._sessions: dict[str | None, Session] = {}
        self._root = Session(self, session_id=None)
        self._sessions[None] = self._root

    @property
    def root(self) -> Session:
        return self._root

    def get_session(self, session_id: str | None) -> Session:
        return self._sessions.get(session_id, self._root)

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
            await self._root.send(
                "Target.detachFromTarget", {"sessionId": session._session_id}
            )
            self._sessions.pop(session._session_id, None)

    async def run(self) -> None:
        try:
            while True:
                msg = await self._transport.recv()
                sid = msg.get("sessionId")
                target = self._sessions.get(sid, self._root)
                await target._handle_message(msg)
        except (ConnectionError, EOFError):
            for session in self._sessions.values():
                for future in session._pending.values():
                    if not future.done():
                        future.set_exception(ConnectionError("Browser pipe closed"))

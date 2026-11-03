"""Chrome's answer to the credential forwarder's challenge, through ``Fetch``.

The :class:`~tellurium.browser.proxy.ProxyForwarder` in front of an
authenticated proxy asks every client for its own secret (``407``). Chrome
cannot answer a proxy challenge on its own, so :class:`ProxyAuth` enables
``Fetch`` with ``handleAuthRequests`` on a browser-wide CDP session: every
paused request is continued at once, and a challenge from the forwarder is
answered with its credentials, once per request. Any other challenge (a
site's ``401``, another proxy) gets Chrome's default answer.

``Fetch`` on the browser session covers every context, page and worker.
It stays on for the whole life of Chrome: a new context has its own auth
cache, so it is challenged again.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger("tellurium")

#: Seconds each ``Fetch`` command may take before it is given up on.
SEND_TIMEOUT = 10.0
#: How many answered challenges are remembered (to cancel a second round).
_ANSWERED_LIMIT = 4096
_LOOPBACK = "127.0.0.1"


class ProxyAuth:
    """Answers the forwarder's ``407`` for Chrome on *session* (a browser session).

    *session* has ``send(method, params, timeout)``, ``on`` and ``off``;
    *forwarder* is started, with ``port`` and ``credentials``. Every command
    in flight is owned here and cancelled by :meth:`stop`.
    """

    def __init__(self, session: Any, forwarder: Any) -> None:
        self._session = session
        self._port: int = forwarder.port
        self._credentials: tuple[str, str] = forwarder.credentials
        self._answered: OrderedDict[str, None] = OrderedDict()
        self._tasks: set[asyncio.Task] = set()
        self._active = False

    def __repr__(self) -> str:
        return f"<ProxyAuth forwarder=127.0.0.1:{self._port} active={self._active}>"

    async def start(self) -> None:
        """Enable ``Fetch`` on the session; on failure nothing stays wired."""
        self._session.on("Fetch.requestPaused", self._on_paused)
        self._session.on("Fetch.authRequired", self._on_auth)
        self._active = True
        try:
            await self._session.send(
                "Fetch.enable",
                {"handleAuthRequests": True, "patterns": [{"urlPattern": "*"}]},
                timeout=SEND_TIMEOUT,
            )
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop answering and cancel every command in flight (idempotent)."""
        if self._active:
            self._active = False
            self._session.off("Fetch.requestPaused", self._on_paused)
            self._session.off("Fetch.authRequired", self._on_auth)
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _on_paused(self, params: dict) -> None:
        self._answer("Fetch.continueRequest", {"requestId": params["requestId"]})

    def _on_auth(self, params: dict) -> None:
        request_id = params["requestId"]
        challenge = params.get("authChallenge") or {}
        if challenge.get("source") != "Proxy" or not self._is_forwarder(challenge):
            response: dict = {"response": "Default"}
        elif request_id in self._answered:
            response = {"response": "CancelAuth"}  # our secret was refused: no loop
        else:
            self._remember(request_id)
            user, secret = self._credentials
            response = {"response": "ProvideCredentials", "username": user, "password": secret}
        self._answer(
            "Fetch.continueWithAuth",
            {"requestId": request_id, "authChallengeResponse": response},
        )

    def _is_forwarder(self, challenge: dict) -> bool:
        try:
            origin = urlsplit(challenge.get("origin") or "")
            return origin.hostname == _LOOPBACK and origin.port == self._port
        except ValueError:
            return False

    def _remember(self, request_id: str) -> None:
        self._answered[request_id] = None
        while len(self._answered) > _ANSWERED_LIMIT:
            self._answered.popitem(last=False)

    def _answer(self, method: str, params: dict) -> None:
        if not self._active:
            return
        task = asyncio.ensure_future(self._send(method, params))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send(self, method: str, params: dict) -> None:
        try:
            await self._session.send(method, params, timeout=SEND_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the request is gone or Chrome is closing
            # Never the params: they may hold the secret.
            logger.debug("ProxyAuth: %s for %s failed: %s", method, params["requestId"], exc)

"""Multiplexer — one CDP endpoint, a pool of Chromes, one Chrome per connection.

Each WebSocket client (Playwright's ``connect_over_cdp``, Puppeteer, a raw
CDP client) gets a Chrome of its own, launched for it with a new seed and the
next proxy, and closed with its profile when it leaves. Chrome stays on its
pipe: the only listening socket is the multiplexer's, on loopback unless told
otherwise, behind a Bearer token kept in ``~/.tellurium/multiplex-token``.

    async with Multiplexer(4, proxies=["http://user:pass@proxy:8080"]) as mux:
        await mux.serve("127.0.0.1", 9339)  # until cancelled (Ctrl-C)
"""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
from pathlib import Path
from typing import Any

from tellurium.access import load_or_create_token
from tellurium.browser.raw_chrome import RawChrome
from tellurium.multiplexer.pool import Pool
from tellurium.multiplexer.server import Server, require_websockets

#: Where the token lives (created 0600 on first use).
TOKEN_FILE = Path("~/.tellurium/multiplex-token")
DEFAULT_PORT = 9339

#: Options of a launch that the pool decides, and why.
_MANAGED = {
    "proxy": "proxies are handed out by the pool: pass proxies=[...]",
    "seed": "each Chrome gets a fresh seed from the pool",
    "user_data_dir": "each Chrome gets a temporary profile, removed when its client leaves",
    "stealth": "the multiplexer relays the client's CDP untouched: no stealth scripts",
}
_LAUNCH_OPTIONS = frozenset(inspect.signature(RawChrome.launch).parameters) - set(_MANAGED)


class Multiplexer:
    """A pool of *size* Chromes behind one CDP endpoint.

    *proxies* are used in turn, one per launched Chrome; *warm* Chromes are
    kept ready with no client; a client waits at most *acquire_timeout*
    seconds for a free place (then HTTP 503). *launch* takes the options of
    :meth:`~tellurium.browser.raw_chrome.RawChrome.launch` (``headless``,
    ``browser``, ``executable``, ``args``, ``geoip``, ``timezone``,
    ``languages``, ...); ``proxy``, ``seed``, ``user_data_dir`` and
    ``stealth`` raise :class:`TypeError`. Needs ``tellurium[multiplex]``.
    """

    def __init__(
        self,
        size: int,
        *,
        proxies: Any = (),
        warm: int = 0,
        acquire_timeout: float = 30,
        **launch: Any,
    ) -> None:
        require_websockets()
        for name in launch:
            if name in _MANAGED:
                raise TypeError(f"Multiplexer() does not take {name!r}: {_MANAGED[name]}")
            if name not in _LAUNCH_OPTIONS:
                raise TypeError(f"Multiplexer() got an unexpected launch option {name!r}")
        if isinstance(proxies, str):
            raise TypeError("proxies must be a list of proxy URLs, not one string")
        if type(size) is not int or size < 1:
            raise ValueError("size must be a positive integer")
        if type(warm) is not int or not 0 <= warm <= size:
            raise ValueError(f"warm must be an integer between 0 and size ({size})")
        if not acquire_timeout > 0:
            raise ValueError("acquire_timeout must be positive")
        self._pool = Pool(
            size,
            proxies=tuple(proxies),
            warm=warm,
            acquire_timeout=float(acquire_timeout),
            launch=dict(launch),
        )
        self._server: Server | None = None
        self._serving: asyncio.Task | None = None
        self._url: str | None = None
        self._token: str | None = None
        self.token_file = TOKEN_FILE.expanduser()

    @property
    def url(self) -> str | None:
        """``http://host:port`` while serving (what ``connect_over_cdp`` takes), else None."""
        return self._url

    @property
    def token(self) -> str | None:
        """The Bearer token clients must send, once :meth:`serve` read it."""
        return self._token

    def status(self) -> dict:
        """Per place: state, pid, proxy without credentials, seed, age, launches,
        restarts, launch failures and last error; in total: clients, queue,
        connections, crashes, hangs and failed launches."""
        return {"url": self._url, **self._pool.status()}

    def restart(self, slot_id: int) -> bool:
        """Replace the Chrome of place *slot_id* (its client gets 1012); False if
        there is no such place or it has no Chrome."""
        for place in self._pool.places:
            if place.id == slot_id and place.chrome is not None:
                place.restart()
                return True
        return False

    async def serve(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
        """Listen on *host*:*port* until cancelled, then close everything:
        the server, the clients (1001), the Chromes, their forwarders and profiles."""
        if self._serving is not None and not self._serving.done():
            raise RuntimeError("this Multiplexer is already serving")
        self._serving = asyncio.current_task()
        self._token = await asyncio.to_thread(load_or_create_token, self.token_file)
        server = Server(self._pool, self._token, host, port)
        self._server = server
        self._pool.start()
        try:
            await server.start()
            self._url = f"http://{_url_host(host)}:{server.port}"
            await asyncio.get_running_loop().create_future()  # until cancelled
        finally:
            self._url = None
            await _finish(self._shutdown(server))

    async def _shutdown(self, server: Server) -> None:
        self._pool.stop_accepting()
        try:
            await server.close()
        finally:
            await self._pool.close()
            self._server = None

    async def close(self) -> None:
        """Stop :meth:`serve` and wait until everything it opened is closed."""
        task = self._serving
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            await asyncio.wait([task])

    async def __aenter__(self) -> Multiplexer:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()


def _url_host(host: str) -> str:
    """How a local client reaches a server bound to *host*."""
    bare = host.strip("[]")
    try:
        address = ipaddress.ip_address(bare)
    except ValueError:
        return "127.0.0.1" if bare in ("", "0") else bare
    if address.is_unspecified:
        return "[::1]" if address.version == 6 else "127.0.0.1"
    return f"[{address}]" if address.version == 6 else str(address)


async def _finish(work: Any) -> None:
    """Run *work* to its end even if cancelled meanwhile; re-raise the
    cancellation afterwards."""
    task = asyncio.ensure_future(work)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError
    task.result()

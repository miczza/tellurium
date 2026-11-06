"""RawChrome — a Chrome process and its CDP pipe, with no :class:`Browser` on top.

For whoever speaks CDP itself (the multiplexer relays a client's messages on
the pipe as they are): no session router, no stealth engine, no session
scripts, no stealth extension, no rewritten User-Agent. The command line comes
from the same :class:`~tellurium.browser.launch_plan.LaunchPlan` as
:meth:`Browser.launch`: engine arguments with the seed, ``--accept-lang``,
``--window-size``, the proxy behind the credential forwarder, WebRTC's UDP kept
inside the proxy, and the time zone and languages of the proxy's exit IP. The
time zone (manual or the exit IP's) also goes in Chrome's ``TZ`` environment
variable: stock Chrome has no flag for it, and nothing here sets it over CDP.

With credentials in the proxy, the forwarder asks Chrome for its own secret
(``407``) and Chrome answers only through CDP ``Fetch``. RawChrome does not
read the pipe, so it does not answer by itself: whoever speaks CDP on the
pipe must call :meth:`RawChrome.answer_proxy_auth` with a browser session of
its own (``Target.attachToBrowserTarget``) before any navigation.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

from tellurium.browser import process as process_module
from tellurium.browser.launch_plan import LaunchPlan
from tellurium.browser.process import BrowserProcess
from tellurium.cdp.transport._base import CDPTransport

#: Seconds Chrome gets to answer its first ``Browser.getVersion`` on the pipe
#: (asked by :meth:`BrowserProcess.spawn`, the only wait for it).
READY_TIMEOUT = process_module.READY_TIMEOUT

#: Id of the ``Browser.close`` sent by :meth:`RawChrome.close` (its reply, if
#: read, matches nothing: the relay draws its ids below ``2**31 - 16``).
_CLOSE_ID = 2**31 - 3
#: Seconds Chrome gets to exit on its own after ``Browser.close``, before the signals.
CLOSE_GRACE = process_module.CLOSE_GRACE


class RawChrome:
    """Chrome on its CDP pipe; :meth:`close` releases it and everything around it.

    Start one with ``await RawChrome.launch(...)`` or
    ``async with RawChrome.launch(...) as raw:``.
    """

    def __init__(self, proc: BrowserProcess, plan: LaunchPlan) -> None:
        self._proc = proc
        self._transport = proc.transport
        self._pid: int = proc.process.pid
        self._seed = plan.seed_used
        self._proxy = plan.proxy
        self._closed = False

    @classmethod
    def launch(
        cls,
        *,
        headless: bool = True,
        browser: str = "stock",
        executable: str | None = None,
        args: list[str] | None = None,
        proxy: str | None = None,
        seed: int | None = None,
        geoip: bool = True,
        timezone: str | None = None,
        languages: list[str] | None = None,
        viewport: tuple[int, int] | None = None,
        webrtc_ip: str | None = None,
        chromium_version: str | None = None,
        chromium_sha256: str | None = None,
        chrome_log: str | Path | None = None,
    ) -> _Launch:
        """Start Chrome with a temporary profile; options as in :meth:`Browser.launch`.

        *geoip* (with a *proxy*) takes the time zone and languages from the
        proxy's exit IP, best effort; *timezone* and *languages* win over it.
        The time zone reaches Chrome as ``TZ`` in its environment (and as
        ``--fingerprint-timezone`` with the patched engine).
        The launch is all-or-nothing: on failure or cancellation Chrome, the
        forwarder and the profile are released, and a Chrome that exits on its
        own raises :class:`~tellurium.browser.launcher.LaunchError` with its
        output. A Chrome that does not answer ``Browser.getVersion`` within
        :data:`READY_TIMEOUT` seconds raises :class:`asyncio.TimeoutError`.
        Options are checked right away (``ValueError``).
        """
        plan = LaunchPlan(
            headless=headless,
            browser=browser,
            executable=executable,
            args=args,
            proxy=proxy,
            seed=seed,
            geoip=geoip,
            proxied_webrtc_only=True,
            timezone=timezone,
            languages=languages,
            viewport=viewport,
            webrtc_ip=webrtc_ip,
            chromium_version=chromium_version,
            chromium_sha256=chromium_sha256,
        )
        return _Launch(cls._start(plan, chrome_log))

    @classmethod
    async def _start(cls, plan: LaunchPlan, chrome_log: str | Path | None) -> RawChrome:
        proc = BrowserProcess()
        try:
            await plan.compose(proc)
            log = Path(chrome_log) if chrome_log is not None else None
            # Stock Chrome has no time zone flag; ICU reads TZ (the patched one gets both).
            tz = plan.effective_timezone
            env = {"TZ": tz} if tz else None
            await proc.spawn(plan.chrome_path, plan.flags, log, env)  # waits for Chrome
        except BaseException as exc:
            try:
                error = await proc.launch_error(exc)
            finally:
                await proc.close()  # every step runs, even if cancelled again
            if error is not None:
                raise error from exc
            raise
        return cls(proc, plan)

    @property
    def transport(self) -> CDPTransport:
        """Chrome's pipe: ``send(bytes)`` (NUL-terminated JSON), ``recv() -> dict``."""
        return self._transport

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def seed(self) -> int | None:
        """The fingerprint seed Chrome got (drawn by the patched engine when none was
        given); None with stock Chrome, which takes none."""
        return self._seed

    @property
    def proxy(self) -> str | None:
        """The proxy as given to :meth:`launch`, credentials included."""
        return self._proxy

    @property
    def needs_proxy_auth(self) -> bool:
        """Whether Chrome goes through the credential forwarder, which wants its
        secret: then nothing loads until :meth:`answer_proxy_auth` is called."""
        return self._proc.forwarder is not None

    async def answer_proxy_auth(self, session: Any) -> None:
        """Have Chrome answer the forwarder's challenge through ``Fetch`` on *session*.

        Call it once, before any navigation. *session* is a browser-wide CDP
        session of the caller's own on this pipe (from
        ``Target.attachToBrowserTarget``) with:

        - ``await send(method, params, timeout)``: sends *method* on that
          session and returns the reply's ``result``, raising on an error
          reply or after *timeout* seconds;
        - ``on(event, handler)`` / ``off(event, handler)``: *handler* is called
          with the event's ``params`` (not the whole message) for each *event*
          on that session.

        The caller keeps reading the pipe and dispatching that session's
        events: a ``Fetch.requestPaused`` nobody hands over leaves its request
        paused for good. A minimal adapter keeps a reader task on
        ``transport.recv()`` that resolves a future per command ``id`` and,
        for a message with no ``id`` and the session's ``sessionId``, calls
        the handlers of its ``method`` with its ``params``.

        ``Fetch`` stays on until :meth:`close`, which stops it. A second call
        while it is on, or a call after :meth:`close`, raises
        :class:`RuntimeError` and changes nothing; after a failed call
        (``Fetch.enable`` refused) another may be made. No-op without
        credentials in the proxy.
        """
        if self._closed:
            raise RuntimeError("this RawChrome is closed")
        current = self._proc.proxy_auth
        if current is not None and current.active:
            raise RuntimeError("this Chrome already answers the proxy's challenge")
        await self._proc.answer_proxy_auth(session)

    @property
    def alive(self) -> bool:
        """False once the Chrome process has exited (or :meth:`close` ran)."""
        process = self._proc.process
        return process is not None and process.poll() is None

    def kill(self) -> None:
        """End Chrome at once, as a crash would (SIGKILL; ``TerminateProcess`` on
        Windows), through the process object, never a pid another process may
        have got since. No-op once it exited; :meth:`close` still releases the
        pipe, the forwarder and the profile."""
        self._proc.kill()

    async def close(self) -> None:
        """Stop Chrome, then release the pipe, the forwarder and the profile.

        Chrome is first asked over the pipe (``Browser.close``, the orderly
        exit that writes the cookie store) and given :data:`CLOSE_GRACE`
        seconds, then SIGTERM, then SIGKILL. Whoever reads the pipe should
        keep reading meanwhile. Bounded in time, safe to call more than once;
        a cancellation (which cuts the grace short) is re-raised once every
        step is done.
        """
        cancelled = False
        try:
            if not self._closed and self.alive:
                asking = asyncio.ensure_future(self._ask_to_close())
                try:
                    await asyncio.shield(asking)
                except asyncio.CancelledError:
                    cancelled = True
                    asking.cancel()
                    await asyncio.wait([asking])
        finally:  # whatever the asking did, the signals and the cleanup follow
            self._closed = True
            try:
                await self._proc.close()
            finally:
                if cancelled:
                    raise asyncio.CancelledError

    async def _ask_to_close(self) -> None:
        """``Browser.close`` on the pipe, then up to :data:`CLOSE_GRACE` seconds
        for Chrome to exit; a send that fails leaves it to the signals."""
        message = json.dumps({"id": _CLOSE_ID, "method": "Browser.close"}).encode() + b"\0"
        try:
            await asyncio.wait_for(self._transport.send(message), 1.0)
        except (TimeoutError, OSError, ConnectionError):
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CLOSE_GRACE
        while self.alive and loop.time() < deadline:
            await asyncio.sleep(0.05)

    async def __aenter__(self) -> RawChrome:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()


class _Launch:
    """What :meth:`RawChrome.launch` returns: await it, or use it with ``async with``."""

    def __init__(self, start: Any) -> None:
        self._start = start
        self._raw: RawChrome | None = None

    def __await__(self) -> Generator[Any, None, RawChrome]:
        return self._start.__await__()

    async def __aenter__(self) -> RawChrome:
        self._raw = await self._start
        return self._raw

    async def __aexit__(self, *exc: Any) -> None:
        if self._raw is not None:
            await self._raw.close()

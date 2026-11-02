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
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

from tellurium.browser.launch_plan import LaunchPlan
from tellurium.browser.process import BrowserProcess
from tellurium.cdp.transport._base import CDPTransport

#: Seconds Chrome gets to answer its first ``Browser.getVersion`` on the pipe.
READY_TIMEOUT = 30.0

#: Id of that first command: replies before the hand-over are read here, and
#: whoever takes the pipe numbers its own commands.
_PROBE_ID = 2**31 - 2


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
        output. Options are checked right away (``ValueError``).
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
            transport = await proc.spawn(plan.chrome_path, plan.flags, log, env)
            await _wait_ready(transport)
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
        """The fingerprint seed Chrome got (drawn by the patched engine when none was given)."""
        return self._seed

    @property
    def proxy(self) -> str | None:
        """The proxy as given to :meth:`launch`, credentials included."""
        return self._proxy

    @property
    def alive(self) -> bool:
        """False once the Chrome process has exited (or :meth:`close` ran)."""
        process = self._proc.process
        return process is not None and process.poll() is None

    async def close(self) -> None:
        """Stop Chrome, then release the pipe, the forwarder and the profile.

        Bounded in time, safe to call more than once; a cancellation is
        re-raised once every step is done.
        """
        await self._proc.close()

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


async def _wait_ready(transport: CDPTransport) -> None:
    """Chrome answers on the pipe; what it says before that is dropped."""
    probe = {"id": _PROBE_ID, "method": "Browser.getVersion"}
    await transport.send(json.dumps(probe).encode() + b"\0")

    async def reply() -> None:
        while (await transport.recv()).get("id") != _PROBE_ID:
            pass

    try:
        await asyncio.wait_for(reply(), READY_TIMEOUT)
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError(
            f"Browser.getVersion got no reply from Chrome within {READY_TIMEOUT:g} s"
        ) from None

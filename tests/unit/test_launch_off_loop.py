"""Launch keeps the event loop free while the binary is resolved (audit m12).

The patched engine's resolution checks for updates over HTTP, may download a
release and hashes a ~300 MB binary: all blocking calls.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from tellurium.browser import engine as engine_mod
from tellurium.browser.browser import Browser
from tellurium.browser.process import BrowserProcess

BLOCK = 0.6


class _Stop(Exception):
    pass


async def test_patched_binary_resolution_runs_off_the_event_loop(monkeypatch):
    def slow_resolve(self):
        time.sleep(BLOCK)  # stands for urllib, the download and the hash
        return "/opt/fake/chrome"

    async def no_spawn(self, *a, **kw):
        raise _Stop

    monkeypatch.setattr(engine_mod.PatchedEngine, "resolve_binary_path", slow_resolve)
    monkeypatch.setattr(BrowserProcess, "spawn", no_spawn)

    gaps = await _loop_gaps_during(Browser.launch(browser="patched", headless=True))
    assert max(gaps) < BLOCK / 2, f"event loop blocked for {max(gaps):.2f}s"


async def test_proxy_geoip_lookup_runs_off_the_event_loop(monkeypatch):
    """The exit-IP lookup goes through the forwarder, which lives on this loop:
    run inline it also starves the forwarder it is waiting for."""
    from tellurium.stealth import geoip

    def slow_exit_ip(proxy, forwarder_port=None):
        time.sleep(BLOCK)
        raise OSError("no network in tests")

    async def no_spawn(self, *a, **kw):
        raise _Stop

    monkeypatch.setattr(geoip, "resolve_exit_ip", slow_exit_ip)
    monkeypatch.setattr(BrowserProcess, "spawn", no_spawn)
    launch = Browser.launch(
        executable="/opt/fake/chrome", headless=True, stealth=True, proxy="http://u:p@127.0.0.1:9"
    )
    gaps = await _loop_gaps_during(launch)
    assert max(gaps) < BLOCK / 2, f"event loop blocked for {max(gaps):.2f}s"


async def _loop_gaps_during(launch) -> list[float]:
    gaps: list[float] = []

    async def ticker() -> None:
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.01)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    tick = asyncio.create_task(ticker())
    try:
        with pytest.raises(_Stop):
            await launch
    finally:
        tick.cancel()
    assert gaps, "the loop never ran during launch"
    return gaps

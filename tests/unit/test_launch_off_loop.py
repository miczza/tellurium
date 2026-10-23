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
            await Browser.launch(browser="patched", headless=True)
    finally:
        tick.cancel()
    assert gaps, "the loop never ran during launch"
    assert max(gaps) < BLOCK / 2, f"event loop blocked for {max(gaps):.2f}s"

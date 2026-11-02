"""health.watch on a fake relay: what counts as a missed probe."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("websockets")

from tellurium.multiplexer import health  # noqa: E402


class FakeChrome:
    alive = True


class FakeRelay:
    """Each probe times out; *talking* says whether messages arrive meanwhile,
    *pause_during* whether the relay holds the pipe for part of the wait."""

    def __init__(self, talking: bool, pause_during: bool = False) -> None:
        self.ended = asyncio.get_running_loop().create_future()
        self.paused = False
        self.pauses = 0
        self.received = 0
        self.talking = talking
        self.pause_during = pause_during
        self.probes = 0

    async def probe(self, timeout: float) -> dict:
        self.probes += 1
        if self.pause_during:  # the pause began before this probe and ends during it
            self.paused = False
        await asyncio.sleep(timeout)
        if self.talking:
            self.received += 50  # the backlog Chrome piled up, read behind the reply
        if self.probes >= 6:
            self.ended.set_result("enough")
        raise TimeoutError


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(health, "INTERVAL", 0.01)
    monkeypatch.setattr(health, "TIMEOUT", 0.01)


async def test_a_probe_behind_a_talking_chrome_is_not_missed():
    relay = FakeRelay(talking=True, pause_during=True)
    relay.paused, relay.pauses = True, 1  # a pause spell under way when probing starts
    kind, _ = await asyncio.wait_for(health.watch(relay, FakeChrome()), 5)
    assert kind == health.CRASH  # it only ended with the pipe, never as a hang
    assert relay.probes == 6


async def test_a_silent_chrome_misses_and_hangs():
    relay = FakeRelay(talking=False)
    kind, reason = await asyncio.wait_for(health.watch(relay, FakeChrome()), 5)
    assert kind == health.HANG and "2 health probes" in reason
    assert relay.probes == health.MISSES

"""LaunchPlan: the Chrome command line, composed before Chrome starts.

``Browser.launch`` keeps its own behaviour (tested by the launch suites); these
cover what the plan offers on top of it: the proxy's time zone and languages and
the proxied-only WebRTC policy without the stealth engine.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from tellurium.browser import engine as engine_mod
from tellurium.browser.launch_plan import LaunchPlan
from tellurium.browser.process import BrowserProcess
from tellurium.stealth import geoip
from tellurium.stealth.geoip import GeoResult

WEBRTC_POLICY = "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"
ROME = GeoResult(country="IT", timezone="Europe/Rome", languages=["it-IT", "it"])


@pytest.fixture(autouse=True)
def fake_executables(monkeypatch):
    async def fake_exec(self):
        return "/bin/true"

    monkeypatch.setattr(engine_mod.StockEngine, "get_executable", fake_exec)
    monkeypatch.setattr(engine_mod.PatchedEngine, "get_executable", fake_exec)


@pytest.fixture
def exit_geo(monkeypatch):
    """The proxy's exit IP is in Rome; records the lookups."""
    lookups: list[tuple] = []

    def fake_exit_ip(proxy, forwarder_port=None, **_kw):
        lookups.append((proxy, forwarder_port))
        return "203.0.113.5"

    monkeypatch.setattr(geoip, "resolve_exit_ip", fake_exit_ip)
    monkeypatch.setattr(geoip, "resolve_geoip", lambda ip, **_kw: ROME)
    return lookups


class SilentProxy:
    """Accepts connections and never answers: a dead proxy that does not refuse."""

    def __init__(self) -> None:
        self.accepted = 0
        self._writers: list = []

    async def __aenter__(self) -> SilentProxy:
        self._server = await asyncio.start_server(self._hold, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()
        for writer in self._writers:
            writer.close()
        await self._server.wait_closed()

    async def _hold(self, reader, writer) -> None:
        self.accepted += 1
        self._writers.append(writer)


async def _flags(**kwargs) -> list[str]:
    proc = BrowserProcess()
    plan = LaunchPlan(headless=True, **kwargs)
    try:
        await plan.compose(proc)
        assert os.path.isdir(plan.profile_dir)
        return plan.flags
    finally:
        await proc.close()


async def test_geoip_without_stealth_takes_timezone_and_languages_from_the_exit_ip(exit_geo):
    flags = await _flags(browser="patched", proxy="http://127.0.0.1:9", geoip=True, seed=7)
    assert "--accept-lang=it-IT,it" in flags
    assert "--fingerprint-timezone=Europe/Rome" in flags
    assert "--fingerprint=7" in flags
    assert exit_geo == [("http://127.0.0.1:9", None)]


async def test_geoip_goes_through_the_credential_forwarder(exit_geo):
    await _flags(proxy="http://user:secret@127.0.0.1:9", geoip=True)
    ((_, port),) = exit_geo
    assert isinstance(port, int) and port > 0


async def test_manual_overrides_win_over_the_exit_ip(exit_geo):
    flags = await _flags(
        browser="patched",
        proxy="http://127.0.0.1:9",
        geoip=True,
        timezone="America/New_York",
        languages=["fr-FR", "fr"],
    )
    assert "--accept-lang=fr-FR,fr" in flags
    assert "--fingerprint-timezone=America/New_York" in flags
    assert not [f for f in flags if "Europe/Rome" in f or "it-IT" in f]


async def test_no_lookup_without_geoip_or_without_proxy(monkeypatch):
    def refuse(*_a, **_kw):
        raise AssertionError("no exit IP lookup expected")

    monkeypatch.setattr(geoip, "resolve_exit_ip", refuse)
    flags = await _flags(proxy="http://127.0.0.1:9")
    assert not [f for f in flags if f.startswith("--accept-lang")]
    await _flags(geoip=True)


async def test_a_failed_lookup_leaves_chrome_defaults(monkeypatch):
    def unreachable(*_a, **_kw):
        raise RuntimeError("no IP echo service answered")

    monkeypatch.setattr(geoip, "resolve_exit_ip", unreachable)
    flags = await _flags(browser="patched", proxy="http://127.0.0.1:9", geoip=True)
    assert not [f for f in flags if f.startswith(("--accept-lang", "--fingerprint-timezone"))]


async def test_proxied_webrtc_policy_without_stealth():
    flags = await _flags(proxy="http://127.0.0.1:9", proxied_webrtc_only=True)
    assert WEBRTC_POLICY in flags
    assert "--proxy-server=http://127.0.0.1:9" in flags


async def test_no_webrtc_policy_without_proxy_or_by_default():
    assert WEBRTC_POLICY not in await _flags(proxied_webrtc_only=True)
    assert WEBRTC_POLICY not in await _flags(proxy="http://127.0.0.1:9")


async def test_the_forwarder_hides_the_credentials():
    proc = BrowserProcess()
    plan = LaunchPlan(headless=True, proxy="http://user:secret@127.0.0.1:9")
    try:
        await plan.compose(proc)
        assert f"--proxy-server=http://127.0.0.1:{proc.forwarder.port}" in plan.flags
        assert not [f for f in plan.flags if "secret" in f]
    finally:
        await proc.close()


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"languages": []}, "languages"),
        ({"viewport": (0, 600)}, "viewport"),
        ({"viewport": (800, 600, 1)}, "viewport"),
    ],
)
def test_invalid_options_are_refused_before_anything_starts(kwargs, match):
    with pytest.raises(ValueError, match=match):
        LaunchPlan(**kwargs)


async def test_a_silent_proxy_costs_at_most_the_geoip_ceiling(monkeypatch, caplog):
    from tellurium.browser import launch_plan

    monkeypatch.setattr(launch_plan, "GEOIP_TIMEOUT", 0.5)
    async with SilentProxy() as proxy:
        started = time.monotonic()
        flags = await _flags(browser="patched", proxy=f"http://127.0.0.1:{proxy.port}", geoip=True)
        elapsed = time.monotonic() - started
    assert proxy.accepted >= 1
    assert elapsed < 3, f"GeoIP took {elapsed:.1f}s"
    assert not [f for f in flags if f.startswith(("--accept-lang", "--fingerprint-timezone"))]
    assert "GeoIP not available" in caplog.text


async def test_a_cancelled_lookup_returns_at_once_and_uses_no_default_executor_thread():
    import threading

    async with SilentProxy() as proxy:
        proc = BrowserProcess()
        plan = LaunchPlan(headless=True, proxy=f"http://user:pw@127.0.0.1:{proxy.port}", geoip=True)
        task = asyncio.ensure_future(plan.compose(proc))
        while not proxy.accepted:
            await asyncio.sleep(0.01)
        lookups = [t for t in threading.enumerate() if t.name == "tellurium-geoip"]
        assert lookups and all(t.daemon for t in lookups)
        started = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - started < 0.5
        await asyncio.wait_for(proc.close(), 10)
        assert not os.path.exists(plan.profile_dir)

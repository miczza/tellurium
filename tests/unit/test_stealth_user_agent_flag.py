"""With stealth, Chrome is launched with the profile's User-Agent.

``Emulation.setUserAgentOverride`` reaches only the requests of the targets it
is sent to: what the browser process loads itself (``Network.loadNetworkResource``,
so robots.txt) leaves with Chrome's own User-Agent unless ``--user-agent`` sets it.
"""

import asyncio
import logging

import pytest

from tellurium.browser import browser as browser_mod
from tellurium.browser import engine as engine_mod
from tellurium.browser.launch_plan import LaunchPlan
from tellurium.browser.process import BrowserProcess
from tellurium.stealth.profile import StealthProfile


def _launch_flags(monkeypatch, version, engine="StockEngine", headless=True, **kw) -> list[str]:
    captured: dict = {}

    def fake_build_chrome_flags(**flags):
        captured.update(flags)
        raise RuntimeError("stop-here")

    async def fake_exec(self):
        return "/bin/true"

    monkeypatch.setattr("tellurium.browser.launch_plan.build_chrome_flags", fake_build_chrome_flags)
    monkeypatch.setattr(getattr(engine_mod, engine), "get_executable", fake_exec)
    monkeypatch.setattr("tellurium.browser.launch_plan.detect_chrome_version", lambda path: version)
    with pytest.raises(RuntimeError, match="stop-here"):
        asyncio.run(browser_mod.Browser.launch(headless=headless, seed=1, **kw))
    return captured["extra_args"]


def test_stealth_launches_chrome_with_the_profile_user_agent_of_the_binary(monkeypatch):
    flags = _launch_flags(monkeypatch, (156, 0, 8078, 47), stealth=True)
    expected = StealthProfile.from_seed(1).with_browser_version("156.0.8078.47").user_agent
    assert "Chrome/156.0.8078.47" in expected
    assert flags.count(f"--user-agent={expected}") == 1


def test_an_undetected_version_gives_no_flag_at_first(monkeypatch):
    """Without the binary's version the profile's default version would go on
    the command line while ``Browser.getVersion`` later moves the override to
    the real one: flag and override would disagree."""
    flags = _launch_flags(monkeypatch, None, stealth=True)
    assert not any(f.startswith("--user-agent=") for f in flags)


async def _composed(monkeypatch, version, browser="stock", stealth=True):
    """A plan composed up to its flags, with *version* read from the binary."""

    async def fake_exec(self):
        return "/opt/fake/chrome"

    monkeypatch.setattr(engine_mod.StockEngine, "get_executable", fake_exec)
    monkeypatch.setattr(engine_mod.PatchedEngine, "get_executable", fake_exec)
    monkeypatch.setattr("tellurium.browser.launch_plan.detect_chrome_version", lambda path: version)
    proc = BrowserProcess()
    plan = LaunchPlan(headless=True, seed=1, stealth=stealth, browser=browser)
    await plan.compose(proc)
    return plan, proc


async def _closing(plan, proc):
    await proc.close()
    if plan.stealth_engine is not None:
        plan.stealth_engine.close()


async def test_an_undetected_version_starts_chrome_again_with_the_flag(monkeypatch):
    """No file tells the version: Chrome is asked (Browser.getVersion) and
    started again with the flag of that version, the profile moved to it."""
    plan, proc = await _composed(monkeypatch, None)
    try:
        assert not any(f.startswith("--user-agent=") for f in plan.flags)
        assert proc.relaunch_with is not None
        flags = proc.relaunch_with("HeadlessChrome/157.0.7400.12")
        expected = StealthProfile.from_seed(1).with_browser_version("157.0.7400.12").user_agent
        assert flags == plan.flags and flags.count(f"--user-agent={expected}") == 1
        assert plan.stealth_profile.browser_version == "157.0.7400.12"
        assert plan.stealth_engine.user_agent_flag() == f"--user-agent={expected}"
        # Same command line as a version read from the binary gives.
        found, found_proc = await _composed(monkeypatch, (157, 0, 7400, 12))
        try:
            assert _without_temp_dirs(flags) == _without_temp_dirs(found.flags)
        finally:
            await _closing(found, found_proc)
    finally:
        await _closing(plan, proc)


def _without_temp_dirs(flags):
    return [f.split("=")[0] if "tellurium_" in f else f for f in flags]


async def test_a_product_without_a_version_keeps_chrome_and_says_why(monkeypatch, caplog):
    plan, proc = await _composed(monkeypatch, None)
    try:
        before = list(plan.flags)
        with caplog.at_level(logging.WARNING, logger="tellurium"):
            assert proc.relaunch_with("SomethingElse") is None
        assert plan.flags == before
        (message,) = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert "robots.txt" in message and "service workers" in message
    finally:
        await _closing(plan, proc)


@pytest.mark.parametrize(
    "case",
    [
        {"version": (156, 0, 8078, 47)},
        {"version": None, "stealth": False},
        {"version": None, "browser": "patched"},
    ],
    ids=["version-read", "no-stealth", "patched"],
)
async def test_no_second_start_when_the_flag_is_not_wanted_or_already_there(monkeypatch, case):
    plan, proc = await _composed(monkeypatch, **case)
    try:
        assert proc.relaunch_with is None
    finally:
        await _closing(plan, proc)


@pytest.mark.parametrize("flag", ["--user-agent=Mine/1.0", "-user-agent=Mine/1.0"])
@pytest.mark.parametrize("backend", ["stock", "patched"])
def test_a_user_agent_of_the_caller_is_refused_with_stealth(monkeypatch, flag, backend):
    """One source for the User-Agent: with stealth the profile's. The caller's
    flag would reach robots.txt while the pages kept the profile's (stock), or
    empty the native client hints (patched)."""

    async def no_exec(self):
        raise AssertionError("refused before anything is resolved or launched")

    monkeypatch.setattr(engine_mod.StockEngine, "get_executable", no_exec)
    monkeypatch.setattr(engine_mod.PatchedEngine, "get_executable", no_exec)
    launch = browser_mod.Browser.launch(stealth=True, browser=backend, args=[flag])
    with pytest.raises(ValueError, match="user-agent in args"):
        asyncio.run(launch)


def test_a_user_agent_of_the_caller_without_stealth_is_kept(monkeypatch):
    flags = _launch_flags(monkeypatch, None, stealth=False, args=["--user-agent=Mine/1.0"])
    assert [f for f in flags if f.startswith("--user-agent=")] == ["--user-agent=Mine/1.0"]


def test_without_stealth_no_user_agent_flag(monkeypatch):
    flags = _launch_flags(monkeypatch, (156, 0, 8078, 47), stealth=False)
    assert not any(f.startswith("--user-agent=") for f in flags)


def test_patched_backend_gets_no_user_agent_flag(monkeypatch):
    """chromium-telluride makes UA and client hints natively: the flag would
    empty its client hints and undo its reduced User-Agent."""
    flags = _launch_flags(
        monkeypatch, (146, 0, 7680, 188), engine="PatchedEngine", stealth=True, browser="patched"
    )
    assert not any(f.startswith("--user-agent=") for f in flags)

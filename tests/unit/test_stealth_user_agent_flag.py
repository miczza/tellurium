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
    monkeypatch.setattr(
        "tellurium.browser.launch_plan._detect_chrome_version", lambda path: version
    )
    with pytest.raises(RuntimeError, match="stop-here"):
        asyncio.run(browser_mod.Browser.launch(headless=headless, seed=1, **kw))
    return captured["extra_args"]


def test_stealth_launches_chrome_with_the_profile_user_agent_of_the_binary(monkeypatch):
    flags = _launch_flags(monkeypatch, (156, 0, 8078, 47), stealth=True)
    expected = StealthProfile.from_seed(1).with_browser_version("156.0.8078.47").user_agent
    assert "Chrome/156.0.8078.47" in expected
    assert flags.count(f"--user-agent={expected}") == 1


def test_an_undetected_version_gives_no_flag(monkeypatch):
    """Without ``--version`` the profile's default version would go on the
    command line while ``Browser.getVersion`` later moves the override to the
    real one: flag and override would disagree."""
    flags = _launch_flags(monkeypatch, None, stealth=True)
    assert not any(f.startswith("--user-agent=") for f in flags)


def _headless_warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "tellurium"
        and r.levelno == logging.WARNING
        and "HeadlessChrome" in r.getMessage()
    ]


def test_an_undetected_version_headless_says_robots_txt_leaves_as_headless(monkeypatch, caplog):
    """No flag, so what the browser loads itself (robots.txt) carries Chrome's
    own headless User-Agent while the pages carry the profile's: said once."""
    with caplog.at_level(logging.WARNING, logger="tellurium"):
        _launch_flags(monkeypatch, None, stealth=True)
    (message,) = _headless_warnings(caplog)
    assert "robots.txt" in message
    assert "--version" in message


@pytest.mark.parametrize(
    "case",
    [
        {"version": (156, 0, 8078, 47), "stealth": True},
        {"version": None, "stealth": True, "headless": False},
        {"version": None, "stealth": False},
        {"version": None, "stealth": True, "engine": "PatchedEngine", "browser": "patched"},
    ],
    ids=["version-read", "headed", "no-stealth", "patched"],
)
def test_no_headless_warning_when_robots_txt_has_the_page_user_agent(monkeypatch, caplog, case):
    with caplog.at_level(logging.WARNING, logger="tellurium"):
        _launch_flags(monkeypatch, **case)
    assert _headless_warnings(caplog) == []


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

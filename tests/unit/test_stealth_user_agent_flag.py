"""With stealth, Chrome is launched with the profile's User-Agent.

``Emulation.setUserAgentOverride`` reaches only the requests of the targets it
is sent to: what the browser process loads itself (``Network.loadNetworkResource``,
so robots.txt) leaves with Chrome's own User-Agent unless ``--user-agent`` sets it.
"""

import asyncio

import pytest

from tellurium.browser import browser as browser_mod
from tellurium.stealth.profile import StealthProfile


def _launch_flags(monkeypatch, version, engine="StockEngine", **kw) -> list[str]:
    captured: dict = {}

    def fake_build_chrome_flags(**flags):
        captured.update(flags)
        raise RuntimeError("stop-here")

    async def fake_exec(self):
        return "/bin/true"

    monkeypatch.setattr(browser_mod, "build_chrome_flags", fake_build_chrome_flags)
    monkeypatch.setattr(getattr(browser_mod, engine), "get_executable", fake_exec)
    monkeypatch.setattr(browser_mod, "_detect_chrome_version", lambda path: version)
    with pytest.raises(RuntimeError, match="stop-here"):
        asyncio.run(browser_mod.Browser.launch(headless=True, seed=1, **kw))
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


def test_a_user_agent_of_the_caller_wins(monkeypatch):
    flags = _launch_flags(monkeypatch, None, stealth=True, args=["--user-agent=Mine/1.0"])
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

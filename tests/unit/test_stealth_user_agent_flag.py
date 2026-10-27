"""With stealth, Chrome is launched with the profile's User-Agent.

``Emulation.setUserAgentOverride`` reaches only the requests of the targets it
is sent to: what the browser process loads itself (``Network.loadNetworkResource``,
so robots.txt) leaves with Chrome's own User-Agent unless ``--user-agent`` sets it.
"""

import asyncio

import pytest

from tellurium.browser import browser as browser_mod
from tellurium.stealth.profile import StealthProfile


def _launch_flags(monkeypatch, version, **kw) -> list[str]:
    captured: dict = {}

    def fake_build_chrome_flags(**flags):
        captured.update(flags)
        raise RuntimeError("stop-here")

    async def fake_exec(self):
        return "/bin/true"

    monkeypatch.setattr(browser_mod, "build_chrome_flags", fake_build_chrome_flags)
    monkeypatch.setattr(browser_mod.StockEngine, "get_executable", fake_exec)
    monkeypatch.setattr(browser_mod, "_detect_chrome_version", lambda path: version)
    with pytest.raises(RuntimeError, match="stop-here"):
        asyncio.run(browser_mod.Browser.launch(headless=True, seed=1, **kw))
    return captured["extra_args"]


def test_stealth_launches_chrome_with_the_profile_user_agent_of_the_binary(monkeypatch):
    flags = _launch_flags(monkeypatch, (156, 0, 8078, 47), stealth=True)
    expected = StealthProfile.from_seed(1).with_browser_version("156.0.8078.47").user_agent
    assert "Chrome/156.0.8078.47" in expected
    assert flags.count(f"--user-agent={expected}") == 1


def test_an_undetected_version_keeps_the_profile_one(monkeypatch):
    flags = _launch_flags(monkeypatch, None, stealth=True)
    assert f"--user-agent={StealthProfile.from_seed(1).user_agent}" in flags


def test_a_user_agent_of_the_caller_wins(monkeypatch):
    flags = _launch_flags(monkeypatch, None, stealth=True, args=["--user-agent=Mine/1.0"])
    assert [f for f in flags if f.startswith("--user-agent=")] == ["--user-agent=Mine/1.0"]


def test_without_stealth_no_user_agent_flag(monkeypatch):
    flags = _launch_flags(monkeypatch, (156, 0, 8078, 47), stealth=False)
    assert not any(f.startswith("--user-agent=") for f in flags)

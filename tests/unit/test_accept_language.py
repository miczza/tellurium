"""Accept-Language must come from --accept-lang, never from a CDP override.

Measured on Chrome 153: Emulation.setUserAgentOverride.acceptLanguage leaks the
raw string into navigator.languages (["en-US", "en;q=0.9"]) and yields a
malformed header ("en-US, en;q=0.9;q=0.9"). With --accept-lang Chrome produces
both natively: header "it-IT,it;q=0.9,en;q=0.8", languages ["it-IT","it","en"].
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from tellurium.stealth.engine import StealthEngine
from tellurium.stealth.profile import StealthProfile


def _engine():
    profile = StealthProfile.from_seed(1)
    backend = MagicMock()
    backend.capabilities.return_value = set()
    return StealthEngine(backend, profile, headless=True, has_proxy=False), profile


def test_user_agent_override_does_not_set_accept_language():
    engine, _ = _engine()
    session = MagicMock()
    session.send = AsyncMock(return_value={})
    asyncio.run(engine.apply_to_session(session))
    ua_calls = [
        c
        for c in session.send.call_args_list
        if c.args and c.args[0] == "Emulation.setUserAgentOverride"
    ]
    assert ua_calls, "expected a setUserAgentOverride call"
    for c in ua_calls:
        assert c.args[1].get("acceptLanguage", "") == ""


def test_launch_flags_include_accept_lang(monkeypatch):
    """Browser.launch(stealth=True) passes --accept-lang=<profile languages>."""
    from tellurium.browser import browser as browser_mod

    captured = {}

    def fake_build_chrome_flags(**kw):
        captured.update(kw)
        raise RuntimeError("stop-here")

    monkeypatch.setattr(browser_mod, "build_chrome_flags", fake_build_chrome_flags)

    async def fake_exec(self):
        return "/bin/true"

    monkeypatch.setattr(browser_mod.StockEngine, "get_executable", fake_exec)
    try:
        asyncio.run(browser_mod.Browser.launch(headless=True, stealth=True, seed=1))
    except RuntimeError as e:
        assert str(e) == "stop-here"
    langs = StealthProfile.from_seed(1).languages
    assert f"--accept-lang={','.join(langs)}" in captured["extra_args"]

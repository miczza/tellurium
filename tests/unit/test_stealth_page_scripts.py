"""Unit tests for StealthEngine.apply_page_scripts (T7)."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest

from tellurium.browser.engine import StockEngine
from tellurium.stealth.engine import StealthEngine
from tellurium.stealth.profile import StealthProfile


@pytest.mark.asyncio
async def test_apply_page_scripts_sends_addScriptToEvaluateOnNewDocument_for_each_script():
    engine = StockEngine()
    profile = StealthProfile.from_seed(42069)
    se = StealthEngine(engine, profile, headless=False, has_proxy=False)

    session = MagicMock()
    session.send = AsyncMock(return_value={"identifier": "stub"})

    await se.apply_page_scripts(session)

    method_calls = [c.args[0] for c in session.send.await_args_list]
    # At least webdriver, chrome_runtime, plugins, webgl, navigator_proto,
    # tostring_mask, keyboard_layout are mandatory in non-proxy/non-headless mode.
    assert method_calls.count("Page.addScriptToEvaluateOnNewDocument") >= 7
    # Every call carries a non-empty `source` string.
    for c in session.send.await_args_list:
        if c.args[0] == "Page.addScriptToEvaluateOnNewDocument":
            assert isinstance(c.args[1]["source"], str) and c.args[1]["source"]
            assert c.args[1].get("runImmediately") is True


@pytest.mark.asyncio
async def test_apply_page_scripts_noop_when_native_navigator():
    """When the engine advertises native_navigator, runtime injection skips."""
    class _FakeEngine:
        def capabilities(self):
            return {"native_fingerprint", "native_navigator"}

    profile = StealthProfile.from_seed(42069)
    se = StealthEngine(_FakeEngine(), profile, headless=False, has_proxy=False)

    session = MagicMock()
    session.send = AsyncMock()

    await se.apply_page_scripts(session)

    # Patched engine — no JS runtime injection needed.
    session.send.assert_not_awaited()

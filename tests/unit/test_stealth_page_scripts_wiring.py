"""Verify Browser.launch invokes apply_page_scripts on the main tab (T7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_launch_calls_apply_page_scripts_when_stock_and_stealth():
    """End-to-end: real stock Chrome + stealth=True should result in
    apply_page_scripts being awaited at least once on a real session."""
    from tellurium import Browser

    original = __import__(
        "tellurium.stealth.engine", fromlist=["StealthEngine"]
    ).StealthEngine.apply_page_scripts
    calls: list = []

    async def spy(self, session):
        calls.append(session)
        return await original(self, session)

    with patch("tellurium.stealth.engine.StealthEngine.apply_page_scripts", spy):
        browser = await Browser.launch(headless=True, stealth=True)
        try:
            assert len(calls) >= 1, "apply_page_scripts was never called"
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_launch_skips_apply_page_scripts_when_stealth_false():
    """stealth=False must not attach the runtime scripts."""
    from tellurium import Browser

    with patch(
        "tellurium.stealth.engine.StealthEngine.apply_page_scripts",
        new=AsyncMock(),
    ) as spy:
        browser = await Browser.launch(headless=True, stealth=False)
        try:
            spy.assert_not_awaited()
        finally:
            await browser.close()

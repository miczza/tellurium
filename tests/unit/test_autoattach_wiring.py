"""Verify T7 auto-attach wiring: root session receives Target.setAutoAttach
and a listener is registered for Target.attachedToTarget."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_launch_calls_setup_auto_attach():
    from tellurium import Browser

    with patch(
        "tellurium.stealth.engine.StealthEngine.setup_auto_attach",
        new=AsyncMock(),
    ) as spy_setup:
        browser = await Browser.launch(headless=True, stealth=True)
        try:
            spy_setup.assert_awaited_once()
            (called_session,), _ = spy_setup.call_args
            assert called_session is browser._router.root
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_launch_registers_target_attached_listener():
    from tellurium import Browser

    browser = await Browser.launch(headless=True, stealth=True)
    try:
        handlers = browser._router.root._event_handlers.get(
            "Target.attachedToTarget", []
        )
        assert len(handlers) >= 1, \
            "No listener registered for Target.attachedToTarget"
    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_patch_and_resume_injects_page_scripts_for_iframe():
    """When _patch_and_resume runs for an iframe, it must push page scripts."""
    from tellurium.browser.engine import StockEngine
    from tellurium.stealth.engine import StealthEngine
    from tellurium.stealth.profile import StealthProfile

    engine = StockEngine()
    profile = StealthProfile.from_seed(42069)
    se = StealthEngine(engine, profile, headless=False, has_proxy=False)

    child = MagicMock()
    child.send = AsyncMock()
    router = MagicMock()
    router.get_session = MagicMock(return_value=child)
    se.set_router(router)

    await se._patch_and_resume(session_id="sess-1", target_type="iframe")

    sent = [c.args[0] for c in child.send.await_args_list]
    # T7.5: stock + headed + non-proxy = 4 core scripts
    # (webdriver, chrome_runtime, plugins, keyboard_layout). Was >=7 pre-T7.5.
    assert sent.count("Page.addScriptToEvaluateOnNewDocument") == 4, \
        f"Expected 4 script injections on iframe, got calls: {sent}"
    # Runtime resume must still happen last
    assert sent[-1] == "Runtime.runIfWaitingForDebugger"

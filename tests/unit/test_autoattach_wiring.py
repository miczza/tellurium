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
            # T7.7: armed on the browser-root session AND on the page session
            # (a root-only auto-attach never fires for a page's OOPIFs /
            # dedicated workers).
            called = [c.args[0] for c in spy_setup.await_args_list]
            assert browser._router.root in called
            assert browser.main_tab._session in called
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_launch_registers_target_attached_listener():
    from tellurium import Browser

    browser = await Browser.launch(headless=True, stealth=True)
    try:
        for session in (browser._router.root, browser.main_tab._session):
            handlers = session._event_handlers.get("Target.attachedToTarget", [])
            assert len(handlers) >= 1, \
                f"No listener registered for Target.attachedToTarget on {session}"
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


def _stock_engine_with_mock_router():
    """Build a StealthEngine (stock caps) whose router returns a mock session."""
    from tellurium.browser.engine import StockEngine
    from tellurium.stealth.engine import StealthEngine
    from tellurium.stealth.profile import StealthProfile

    se = StealthEngine(
        StockEngine(), StealthProfile.from_seed(42069),
        headless=False, has_proxy=False,
    )
    child = MagicMock()
    child.send = AsyncMock()
    router = MagicMock()
    router.get_session = MagicMock(return_value=child)
    se.set_router(router)
    return se, child


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_type", ["worker", "service_worker", "shared_worker"],
)
async def test_patch_and_resume_injects_worker_scripts(target_type):
    """T7.7 §P1.2: worker targets get Runtime.evaluate injection + resume.

    Workers have no Page domain, so Page.addScriptToEvaluateOnNewDocument
    must NOT be used for them.
    """
    se, child = _stock_engine_with_mock_router()

    await se._patch_and_resume("sess-w", target_type, "blob:http://x/abc")

    sent = [c.args[0] for c in child.send.await_args_list]
    assert "Page.addScriptToEvaluateOnNewDocument" not in sent
    assert sent.count("Runtime.evaluate") == 1
    assert sent[-1] == "Runtime.runIfWaitingForDebugger"

    source = child.send.await_args_list[0].args[1]["expression"]
    # Marker / toString-mask scheme (same as webdriver.js)
    assert "hardwareConcurrency" in source
    # Never define navigator.webdriver in worker scope — WorkerNavigator has
    # no such property in real Chrome. (Comments mentioning it are fine;
    # what must be absent is a defineProperty for it.)
    code = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("//")
    )
    assert "webdriver" not in code


@pytest.mark.asyncio
async def test_patch_and_resume_skips_extension_workers():
    se, child = _stock_engine_with_mock_router()

    await se._patch_and_resume(
        "sess-x", "service_worker", "chrome-extension://abc/sw.js",
    )

    sent = [c.args[0] for c in child.send.await_args_list]
    assert sent == ["Runtime.runIfWaitingForDebugger"]


@pytest.mark.asyncio
async def test_patch_and_resume_resumes_even_when_injection_fails():
    """A frozen target must never be left waiting for the debugger."""
    se, child = _stock_engine_with_mock_router()

    async def _boom(method, params=None, **kw):
        if method != "Runtime.runIfWaitingForDebugger":
            raise RuntimeError("injection exploded")
        return {}

    child.send = AsyncMock(side_effect=_boom)

    await se._patch_and_resume("sess-1", "iframe")

    sent = [c.args[0] for c in child.send.await_args_list]
    assert sent[-1] == "Runtime.runIfWaitingForDebugger"


@pytest.mark.asyncio
async def test_on_target_attached_uses_running_loop():
    """_on_target_attached is called from the dispatch loop; it must not rely
    on the deprecated asyncio.get_event_loop()."""
    se, child = _stock_engine_with_mock_router()
    se._router._sessions = {}

    se._on_target_attached({
        "sessionId": "s1",
        "targetInfo": {"type": "worker", "url": "blob:http://x/1"},
    })
    # Let the created task run to completion
    import asyncio as _asyncio
    await _asyncio.sleep(0)
    await _asyncio.sleep(0)

    sent = [c.args[0] for c in child.send.await_args_list]
    assert "Runtime.runIfWaitingForDebugger" in sent

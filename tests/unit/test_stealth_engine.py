import asyncio
import os
import shutil
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tellurium.browser.engine import StockEngine, PatchedEngine
from tellurium.stealth.profile import StealthProfile
from tellurium.stealth.engine import StealthEngine


def _make_profile(**overrides):
    defaults = dict(
        seed=42069,
        user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/146.0.7680.188 Safari/537.36",
        browser_version="146.0.7680.188",
        platform="Linux x86_64",
        platform_version="",
        target_os="linux",
        ch_ua='"Chromium";v="146", "Google Chrome";v="146", "Not-A.Brand";v="99"',
        ch_ua_platform="Linux",
        ch_ua_arch="x86",
        ch_ua_bitness="64",
        ch_ua_full_version_list='"Chromium";v="146.0.7680.188"',
        ch_ua_mobile=False,
        screen_width=1920,
        screen_height=1080,
        screen_avail_height=1050,
        device_pixel_ratio=1.0,
        hardware_concurrency=8,
        device_memory=8,
        webgl_vendor="Mesa",
        webgl_renderer="OpenGL 4.6",
        languages=["en-US", "en"],
        timezone="America/Chicago",
        locale="en-US",
        accept_language="en-US, en;q=0.9",
    )
    defaults.update(overrides)
    return StealthProfile(**defaults)


# ---------------------------------------------------------------------------
# Constructor / capability routing
# ---------------------------------------------------------------------------

def test_stock_engine_no_native_caps():
    engine = StockEngine()
    se = StealthEngine(engine, _make_profile(), headless=False, has_proxy=False)
    assert "native_fingerprint" not in se._caps


def test_patched_engine_has_native_caps():
    engine = PatchedEngine()
    se = StealthEngine(engine, _make_profile(), headless=False, has_proxy=False)
    assert "native_fingerprint" in se._caps
    assert "native_navigator" in se._caps


# ---------------------------------------------------------------------------
# build_extension
# ---------------------------------------------------------------------------

def test_build_extension_stock_returns_path():
    engine = StockEngine()
    se = StealthEngine(engine, _make_profile(), headless=False, has_proxy=False)
    ext_dir = se.build_extension()
    assert ext_dir is not None
    assert os.path.isdir(ext_dir)
    assert os.path.isfile(os.path.join(ext_dir, "manifest.json"))
    assert os.path.isfile(os.path.join(ext_dir, "content.js"))
    shutil.rmtree(ext_dir)


def test_build_extension_patched_returns_none():
    engine = PatchedEngine()
    se = StealthEngine(engine, _make_profile(), headless=False, has_proxy=False)
    assert se.build_extension() is None


def test_build_extension_headless_includes_headless_scripts():
    engine = StockEngine()
    se = StealthEngine(engine, _make_profile(), headless=True, has_proxy=False)
    ext_dir = se.build_extension()
    with open(os.path.join(ext_dir, "content.js")) as f:
        content = f.read()
    # Headless scripts should be included
    assert "outerWidth" in content or "Notification" in content or "connection" in content
    shutil.rmtree(ext_dir)


def test_build_extension_proxy_includes_webrtc():
    engine = StockEngine()
    se = StealthEngine(engine, _make_profile(), headless=False, has_proxy=True)
    ext_dir = se.build_extension()
    with open(os.path.join(ext_dir, "content.js")) as f:
        content = f.read()
    assert "RTC" in content or "webrtc" in content.lower() or "rtc" in content.lower()
    shutil.rmtree(ext_dir)


# ---------------------------------------------------------------------------
# _build_scripts
# ---------------------------------------------------------------------------

def test_build_scripts_stock_includes_core():
    engine = StockEngine()
    se = StealthEngine(engine, _make_profile(), headless=False, has_proxy=False)
    scripts = se._build_scripts()
    assert len(scripts) == 7  # 7 core scripts


def test_build_scripts_stock_headless_proxy():
    engine = StockEngine()
    se = StealthEngine(engine, _make_profile(), headless=True, has_proxy=True)
    scripts = se._build_scripts()
    # 7 core + 1 webrtc + 5 headless = 13
    assert len(scripts) == 13


def test_build_scripts_patched_returns_empty():
    engine = PatchedEngine()
    se = StealthEngine(engine, _make_profile(), headless=True, has_proxy=True)
    scripts = se._build_scripts()
    assert scripts == []


# ---------------------------------------------------------------------------
# apply_to_session (async)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apply_to_session_stock_calls_ua_override():
    engine = StockEngine()
    profile = _make_profile()
    se = StealthEngine(engine, profile, headless=False, has_proxy=False)

    session = AsyncMock()
    await se.apply_to_session(session)

    methods_called = [call.args[0] for call in session.send.call_args_list]
    assert "Emulation.setUserAgentOverride" in methods_called
    assert "Emulation.setTimezoneOverride" in methods_called
    assert "Emulation.setLocaleOverride" in methods_called
    assert "Emulation.setHardwareConcurrencyOverride" in methods_called


@pytest.mark.asyncio
async def test_apply_to_session_stock_timezone_params():
    engine = StockEngine()
    profile = _make_profile(timezone="Europe/Berlin", locale="de-DE")
    se = StealthEngine(engine, profile, headless=False, has_proxy=False)

    session = AsyncMock()
    await se.apply_to_session(session)

    # Check timezone call
    for call in session.send.call_args_list:
        if call.args[0] == "Emulation.setTimezoneOverride":
            assert call.args[1]["timezoneId"] == "Europe/Berlin"
        if call.args[0] == "Emulation.setLocaleOverride":
            assert call.args[1]["locale"] == "de-DE"


@pytest.mark.asyncio
async def test_apply_to_session_patched_skips_ua_override():
    engine = PatchedEngine()
    profile = _make_profile()
    se = StealthEngine(engine, profile, headless=False, has_proxy=False)

    session = AsyncMock()
    await se.apply_to_session(session)

    methods_called = [call.args[0] for call in session.send.call_args_list]
    # Patched: no UA override or hardware concurrency override
    assert "Emulation.setUserAgentOverride" not in methods_called
    assert "Emulation.setHardwareConcurrencyOverride" not in methods_called
    # But timezone/locale always applied
    assert "Emulation.setTimezoneOverride" in methods_called
    assert "Emulation.setLocaleOverride" in methods_called


@pytest.mark.asyncio
async def test_apply_to_session_headless_fixes():
    engine = StockEngine()
    profile = _make_profile()
    se = StealthEngine(engine, profile, headless=True, has_proxy=False)

    session = AsyncMock()
    await se.apply_to_session(session)

    methods_called = [call.args[0] for call in session.send.call_args_list]
    assert "Emulation.setFocusEmulationEnabled" in methods_called
    assert "Emulation.setDeviceMetricsOverride" in methods_called
    assert "Emulation.setEmulatedMedia" in methods_called


@pytest.mark.asyncio
async def test_apply_to_session_no_headless_fixes_when_headed():
    engine = StockEngine()
    profile = _make_profile()
    se = StealthEngine(engine, profile, headless=False, has_proxy=False)

    session = AsyncMock()
    await se.apply_to_session(session)

    methods_called = [call.args[0] for call in session.send.call_args_list]
    assert "Emulation.setFocusEmulationEnabled" not in methods_called
    assert "Emulation.setDeviceMetricsOverride" not in methods_called


@pytest.mark.asyncio
async def test_apply_headless_device_metrics():
    engine = StockEngine()
    profile = _make_profile(
        screen_width=1920, screen_height=1080,
        screen_avail_height=1050, device_pixel_ratio=2.0,
    )
    se = StealthEngine(engine, profile, headless=True, has_proxy=False)

    session = AsyncMock()
    await se.apply_to_session(session)

    for call in session.send.call_args_list:
        if call.args[0] == "Emulation.setDeviceMetricsOverride":
            params = call.args[1]
            assert params["width"] == 1920
            assert params["height"] == 1050  # avail height
            assert params["screenWidth"] == 1920
            assert params["screenHeight"] == 1080
            assert params["deviceScaleFactor"] == 2.0


# ---------------------------------------------------------------------------
# setup_auto_attach
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_auto_attach_stock_waits_for_debugger():
    engine = StockEngine()
    se = StealthEngine(engine, _make_profile(), headless=False, has_proxy=False)

    session = AsyncMock()
    await se.setup_auto_attach(session)

    session.send.assert_called_once_with("Target.setAutoAttach", {
        "autoAttach": True,
        "waitForDebuggerOnStart": True,
        "flatten": True,
    })
    session.on.assert_called_once_with("Target.attachedToTarget", se._on_target_attached)


@pytest.mark.asyncio
async def test_setup_auto_attach_patched_no_wait():
    engine = PatchedEngine()
    se = StealthEngine(engine, _make_profile(), headless=False, has_proxy=False)

    session = AsyncMock()
    await se.setup_auto_attach(session)

    session.send.assert_called_once_with("Target.setAutoAttach", {
        "autoAttach": True,
        "waitForDebuggerOnStart": False,
        "flatten": True,
    })
    # No event handler registered for patched
    session.on.assert_not_called()


# ---------------------------------------------------------------------------
# set_router / _get_session
# ---------------------------------------------------------------------------

def test_set_router_and_get_session():
    engine = StockEngine()
    se = StealthEngine(engine, _make_profile(), headless=False, has_proxy=False)

    mock_router = MagicMock()
    mock_session = MagicMock()
    mock_router.get_session.return_value = mock_session

    se.set_router(mock_router)
    result = se._get_session("test-session-id")

    mock_router.get_session.assert_called_once_with("test-session-id")
    assert result is mock_session


# ---------------------------------------------------------------------------
# UA override parameters
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ua_override_params():
    engine = StockEngine()
    profile = _make_profile(browser_version="146.0.7680.188")
    se = StealthEngine(engine, profile, headless=False, has_proxy=False)

    session = AsyncMock()
    await se._set_ua_override(session)

    call_args = session.send.call_args
    assert call_args.args[0] == "Emulation.setUserAgentOverride"
    params = call_args.args[1]
    assert params["userAgent"] == profile.user_agent
    assert params["platform"] == profile.platform
    meta = params["userAgentMetadata"]
    assert meta["platform"] == profile.ch_ua_platform
    assert meta["architecture"] == profile.ch_ua_arch
    assert meta["bitness"] == profile.ch_ua_bitness
    assert meta["mobile"] == profile.ch_ua_mobile
    # Major version in brands
    assert any(b["version"] == "146" for b in meta["brands"])

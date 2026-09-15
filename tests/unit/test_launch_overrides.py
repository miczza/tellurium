"""Browser.launch manual overrides: timezone, languages, viewport, mouse_profile.

Design doc 01 §"Override manuali (ignorano auto-detect)" — these always win
over GeoIP and over the seeded StealthProfile defaults.
"""
from __future__ import annotations

import asyncio

import pytest

from tellurium.browser import browser as browser_mod
from tellurium.stealth.profile import StealthProfile


@pytest.fixture
def captured_flags(monkeypatch):
    """Run launch() up to flag assembly, then abort and hand back the kwargs."""
    captured: dict = {}

    def fake_build_chrome_flags(**kw):
        captured.update(kw)
        raise RuntimeError("stop-here")

    monkeypatch.setattr(browser_mod, "build_chrome_flags", fake_build_chrome_flags)

    async def fake_exec(self):
        return "/bin/true"

    monkeypatch.setattr(browser_mod.StockEngine, "get_executable", fake_exec)
    return captured


def _launch(**kwargs):
    try:
        asyncio.run(browser_mod.Browser.launch(**kwargs))
    except RuntimeError as exc:
        if str(exc) != "stop-here":
            raise
        return
    raise AssertionError("launch() did not reach build_chrome_flags")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_unknown_mouse_profile_is_rejected():
    with pytest.raises(ValueError, match="mouse_profile"):
        asyncio.run(browser_mod.Browser.launch(mouse_profile="reckless"))


def test_empty_languages_list_is_rejected():
    with pytest.raises(ValueError, match="languages"):
        asyncio.run(browser_mod.Browser.launch(languages=[]))


@pytest.mark.parametrize("bad", [(0, 600), (800, -1), (800, 600, 1)])
def test_invalid_viewport_is_rejected(bad):
    with pytest.raises(ValueError, match="viewport"):
        asyncio.run(browser_mod.Browser.launch(viewport=bad))


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


def test_languages_override_reaches_accept_lang_without_stealth(captured_flags):
    _launch(headless=True, languages=["it-IT", "it", "en"])
    assert "--accept-lang=it-IT,it,en" in captured_flags["extra_args"]


def test_languages_override_wins_over_the_stealth_profile(captured_flags):
    _launch(headless=True, stealth=True, seed=1, languages=["fr-FR", "fr"])
    extra = captured_flags["extra_args"]
    assert "--accept-lang=fr-FR,fr" in extra
    profile_langs = ",".join(StealthProfile.from_seed(1).languages)
    assert f"--accept-lang={profile_langs}" not in extra


def test_no_accept_lang_flag_when_nothing_is_requested(captured_flags):
    _launch(headless=True)
    assert not [a for a in captured_flags["extra_args"] if a.startswith("--accept-lang")]


def test_viewport_becomes_window_size(captured_flags):
    _launch(headless=True, viewport=(1280, 720))
    assert "--window-size=1280,720" in captured_flags["extra_args"]


def test_viewport_does_not_use_device_metrics_flags(captured_flags):
    _launch(headless=True, viewport=(1280, 720))
    assert not [a for a in captured_flags["extra_args"] if "device-scale" in a]


# ---------------------------------------------------------------------------
# StealthProfile precedence
# ---------------------------------------------------------------------------


def _profile_from_launch(monkeypatch, **kwargs):
    """Capture the StealthProfile handed to StealthEngine during launch()."""
    seen: dict = {}

    # launch() imports StealthEngine lazily, so patching the module attribute
    # is enough to intercept the profile it is constructed with.
    import tellurium.stealth.engine as engine_mod

    class _SpyEngine(engine_mod.StealthEngine):
        def __init__(self, backend, profile, headless, has_proxy):
            seen["profile"] = profile
            super().__init__(backend, profile, headless, has_proxy)

    monkeypatch.setattr(engine_mod, "StealthEngine", _SpyEngine)

    def fake_build_chrome_flags(**kw):
        raise RuntimeError("stop-here")

    monkeypatch.setattr(browser_mod, "build_chrome_flags", fake_build_chrome_flags)

    async def fake_exec(self):
        return "/bin/true"

    monkeypatch.setattr(browser_mod.StockEngine, "get_executable", fake_exec)
    try:
        asyncio.run(browser_mod.Browser.launch(stealth=True, seed=1, **kwargs))
    except RuntimeError as exc:
        if str(exc) != "stop-here":
            raise
    return seen["profile"]


def test_timezone_override_replaces_the_profile_timezone(monkeypatch):
    profile = _profile_from_launch(monkeypatch, timezone="Europe/Rome")
    assert profile.timezone == "Europe/Rome"
    assert profile.timezone != StealthProfile.from_seed(1).timezone


def test_languages_override_rebuilds_locale_and_accept_language(monkeypatch):
    profile = _profile_from_launch(monkeypatch, languages=["it-IT", "it", "en"])
    assert profile.languages == ["it-IT", "it", "en"]
    assert profile.locale == "it-IT"
    assert profile.accept_language == "it-IT, it;q=0.9, en;q=0.8"


def test_profile_is_untouched_without_overrides(monkeypatch):
    profile = _profile_from_launch(monkeypatch)
    expected = StealthProfile.from_seed(1)
    assert profile.timezone == expected.timezone
    assert profile.languages == expected.languages


# ---------------------------------------------------------------------------
# Timezone override without stealth
# ---------------------------------------------------------------------------


async def test_manual_timezone_override_is_sent_to_the_session():
    from unittest.mock import AsyncMock, MagicMock

    browser = browser_mod.Browser()
    browser._timezone_override = "Asia/Tokyo"
    session = MagicMock()
    session.send = AsyncMock(return_value={})
    await browser._apply_manual_overrides(session)
    session.send.assert_awaited_once_with(
        "Emulation.setTimezoneOverride", {"timezoneId": "Asia/Tokyo"}
    )


async def test_no_override_means_no_cdp_traffic():
    from unittest.mock import AsyncMock, MagicMock

    browser = browser_mod.Browser()
    session = MagicMock()
    session.send = AsyncMock(return_value={})
    await browser._apply_manual_overrides(session)
    session.send.assert_not_awaited()


async def test_a_rejected_timezone_does_not_break_launch(caplog):
    from unittest.mock import AsyncMock, MagicMock

    browser = browser_mod.Browser()
    browser._timezone_override = "Not/AZone"
    session = MagicMock()
    session.send = AsyncMock(side_effect=RuntimeError("Invalid timezone"))
    with caplog.at_level("WARNING", logger="tellurium"):
        await browser._apply_manual_overrides(session)
    assert "Not/AZone" in caplog.text


# ---------------------------------------------------------------------------
# mouse_profile plumbing
# ---------------------------------------------------------------------------


async def test_new_tab_inherits_the_browser_mouse_profile():
    from unittest.mock import AsyncMock, MagicMock

    browser = browser_mod.Browser()
    browser._mouse_profile = "careful"
    browser._router = MagicMock()
    browser._router.root.send = AsyncMock(return_value={"targetId": "T2"})
    session = MagicMock()
    session.send = AsyncMock(return_value={})
    session.on = MagicMock()
    browser._router.attach = AsyncMock(return_value=session)

    tab = await browser.new_tab()
    assert tab._mouse_profile == "careful"

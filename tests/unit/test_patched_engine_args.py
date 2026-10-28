"""PatchedEngine passes the timezone natively: ``--fingerprint-timezone=<IANA>``.

Only the patched engine emits it, and only when a timezone is known (the
stealth profile, or the manual ``timezone=`` of ``launch`` with stealth off).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from types import SimpleNamespace

import pytest

from tellurium.browser._manifest import current_platform
from tellurium.browser.engine import PatchedEngine, StockEngine

FLAG = "--fingerprint-timezone"


def _tz_flags(args: list[str]) -> list[str]:
    return [a for a in args if a.startswith(FLAG)]


def test_profile_timezone_becomes_the_flag():
    engine = PatchedEngine()
    profile = SimpleNamespace(seed=42069, target_os="linux", timezone="Europe/Berlin")
    args = engine.build_args(profile)
    assert args == [
        "--fingerprint=42069",
        "--fingerprint-platform=linux",
        "--fingerprint-timezone=Europe/Berlin",
    ]


@pytest.mark.parametrize(
    "tz",
    [
        "UTC",
        "America/Argentina/Buenos_Aires",
        "Etc/GMT+3",
        "America/Port-au-Prince",
        # ICU custom ids, which Emulation.setTimezoneOverride accepts too.
        "GMT+05:30",
        "GMT-3",
        "GMT+0530",
        "GMT-12:00",
        "gmt+5",
    ],
)
def test_plausible_iana_ids_pass(tz):
    args = PatchedEngine().build_args(SimpleNamespace(seed=1, timezone=tz))
    assert _tz_flags(args) == [f"{FLAG}={tz}"]


def test_no_timezone_no_flag():
    engine = PatchedEngine(seed=7)
    assert _tz_flags(engine.build_args(None)) == []
    assert _tz_flags(engine.build_args(SimpleNamespace(seed=1, timezone=None))) == []
    assert _tz_flags(engine.build_args(SimpleNamespace(seed=1))) == []


@pytest.mark.parametrize(
    "tz",
    [
        "",
        "Europe/ Rome",
        "Europe/Rome --no-sandbox",
        "a=b",
        "x\ny",
        "Europe/Rome:00",
        "GMT+24:00",
        "GMT+05:60",
        "GMT+5:3",
        "GMT05:30",
    ],
)
def test_implausible_timezone_is_not_a_flag(tz, caplog):
    with caplog.at_level(logging.WARNING, logger="tellurium"):
        args = PatchedEngine().build_args(SimpleNamespace(seed=1, timezone=tz))
    assert _tz_flags(args) == []
    assert args[0] == "--fingerprint=1"
    messages = [r.getMessage().lower() for r in caplog.records]
    assert any("timezone" in m and "host" in m for m in messages)


def test_seed_none_in_namespace_keeps_engine_seed():
    """Without stealth launch passes ``SimpleNamespace(seed=None, timezone=...)``."""
    engine = PatchedEngine(seed=99)
    args = engine.build_args(SimpleNamespace(seed=None, timezone="Asia/Tokyo"))
    assert args == ["--fingerprint=99", f"{FLAG}=Asia/Tokyo"]


def test_stock_engine_never_gets_the_flag():
    engine = StockEngine()
    assert engine.build_args(SimpleNamespace(seed=1, timezone="Europe/Rome")) == []
    assert "native_timezone" not in engine.capabilities()


# ---------------------------------------------------------------------------
# native_timezone: only when the MANIFEST says the binary reads the flag
# ---------------------------------------------------------------------------

VERSION = "152.0.0.1"


def _install(tmp_path, supported_flags):
    """A cache with one version, its binary and a MANIFEST listing *supported_flags*."""
    root = tmp_path / "chromium"
    version_dir = root / VERSION
    version_dir.mkdir(parents=True)
    binary = version_dir / "chrome"
    binary.write_bytes(b"binary")
    manifest = {
        "version": "0.2.0",
        "binary_sha256": {current_platform(): hashlib.sha256(b"binary").hexdigest()},
        "supported_flags": supported_flags,
    }
    (version_dir / "MANIFEST.json").write_text(json.dumps(manifest))
    return root


def test_native_timezone_absent_before_the_binary_is_known():
    assert "native_timezone" not in PatchedEngine().capabilities()
    assert "native_timezone" not in PatchedEngine(executable="/bin/true").capabilities()


def test_native_timezone_when_manifest_lists_the_flag(tmp_path):
    root = _install(tmp_path, ["--fingerprint", "--fingerprint-timezone"])
    engine = PatchedEngine(cache_root=root, chromium_version=VERSION)
    engine.resolve_binary_path()
    assert "native_timezone" in engine.capabilities()


def test_no_native_timezone_when_manifest_omits_the_flag(tmp_path):
    """Binaries 146 declare only --fingerprint/-platform/-webrtc-ip."""
    root = _install(
        tmp_path, ["--fingerprint", "--fingerprint-platform", "--fingerprint-webrtc-ip"]
    )
    engine = PatchedEngine(cache_root=root, chromium_version=VERSION)
    engine.resolve_binary_path()
    caps = engine.capabilities()
    assert "native_timezone" not in caps
    assert "native_fingerprint" in caps
    # The flag is passed anyway: a binary that does not know it ignores it.
    args = engine.build_args(SimpleNamespace(seed=1, timezone="Europe/Rome"))
    assert _tz_flags(args) == [f"{FLAG}=Europe/Rome"]


def test_no_native_timezone_without_manifest(tmp_path):
    root = tmp_path / "chromium"
    (root / VERSION).mkdir(parents=True)
    (root / VERSION / "chrome").write_bytes(b"binary")
    engine = PatchedEngine(cache_root=root, chromium_version=VERSION)
    engine.resolve_binary_path()
    assert "native_timezone" not in engine.capabilities()


# ---------------------------------------------------------------------------
# Browser.launch(browser="patched") -> --fingerprint-timezone value
# ---------------------------------------------------------------------------


def _launch_engine_args(monkeypatch, engine_cls, **launch_kwargs) -> list[str]:
    """Run launch() up to the Chrome flags; return what the engine emitted."""
    from tellurium.browser import browser as browser_mod

    captured: list[str] = []
    real_build_args = engine_cls.build_args

    def spy_build_args(self, profile):
        args = real_build_args(self, profile)
        captured.extend(args)
        return args

    async def fake_exec(self):
        return "/bin/true"

    def stop(**_kw):
        raise RuntimeError("stop-here")

    monkeypatch.setattr(engine_cls, "build_args", spy_build_args)
    monkeypatch.setattr(engine_cls, "get_executable", fake_exec)
    monkeypatch.setattr(browser_mod, "build_chrome_flags", stop)
    with pytest.raises(RuntimeError, match="stop-here"):
        asyncio.run(browser_mod.Browser.launch(headless=True, **launch_kwargs))
    return captured


def test_launch_without_stealth_passes_manual_timezone(monkeypatch):
    args = _launch_engine_args(
        monkeypatch, PatchedEngine, browser="patched", stealth=False, timezone="Europe/Rome"
    )
    assert _tz_flags(args) == [f"{FLAG}=Europe/Rome"]
    assert any(a.startswith("--fingerprint=") for a in args)


def test_launch_without_stealth_and_seed_passes_both(monkeypatch):
    args = _launch_engine_args(
        monkeypatch,
        PatchedEngine,
        browser="patched",
        stealth=False,
        seed=5,
        timezone="Asia/Tokyo",
    )
    assert args == ["--fingerprint=5", f"{FLAG}=Asia/Tokyo"]


def test_launch_without_stealth_or_timezone_has_no_flag(monkeypatch):
    args = _launch_engine_args(monkeypatch, PatchedEngine, browser="patched", stealth=False)
    assert _tz_flags(args) == []


def test_launch_with_stealth_manual_timezone_wins(monkeypatch):
    args = _launch_engine_args(
        monkeypatch,
        PatchedEngine,
        browser="patched",
        stealth=True,
        seed=3,
        timezone="Africa/Cairo",
    )
    assert _tz_flags(args) == [f"{FLAG}=Africa/Cairo"]


def test_launch_with_stealth_uses_profile_timezone(monkeypatch):
    from tellurium.stealth.profile import StealthProfile

    expected = StealthProfile.from_seed(3).timezone
    args = _launch_engine_args(monkeypatch, PatchedEngine, browser="patched", stealth=True, seed=3)
    assert _tz_flags(args) == [f"{FLAG}={expected}"]


def test_launch_stock_has_no_flag(monkeypatch):
    args = _launch_engine_args(monkeypatch, StockEngine, stealth=False, timezone="Europe/Rome")
    assert args == []

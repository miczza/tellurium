"""Tests for WebRTC IP resolution pipeline (review 2026-04-15 #9)."""

import pytest

from tellurium.stealth._webrtc import resolve_webrtc_ip


def test_resolve_webrtc_ip_disable_returns_none():
    """'disable' setting must return None (no spoofing)."""
    assert resolve_webrtc_ip("disable", proxy=None) is None


def test_resolve_webrtc_ip_literal_ip_passthrough():
    """An explicit IPv4/IPv6 literal must be returned verbatim."""
    assert resolve_webrtc_ip("203.0.113.42", proxy=None) == "203.0.113.42"
    assert resolve_webrtc_ip("2001:db8::1", proxy=None) == "2001:db8::1"


def test_resolve_webrtc_ip_auto_uses_proxy_ip(monkeypatch):
    """'auto' with a proxy URL must resolve the proxy host to an IP."""
    monkeypatch.setattr(
        "socket.gethostbyname",
        lambda host: (
            "198.51.100.7" if host == "proxy.example.com" else (_ for _ in ()).throw(OSError)
        ),
    )
    ip = resolve_webrtc_ip("auto", proxy="http://proxy.example.com:8080")
    assert ip == "198.51.100.7"


def test_resolve_webrtc_ip_auto_without_proxy_raises():
    """'auto' without a proxy is a misconfiguration — raise ValueError."""
    with pytest.raises(ValueError, match="webrtc_ip='auto' requires proxy="):
        resolve_webrtc_ip("auto", proxy=None)


def test_auto_with_a_proxy_without_host_keeps_the_password_out_of_the_error():
    with pytest.raises(ValueError, match="host name") as info:
        resolve_webrtc_ip("auto", proxy="http://user:s3cret@:8080")
    assert "s3cret" not in str(info.value)
    assert "user" not in str(info.value)


def test_resolve_webrtc_ip_invalid_setting_raises():
    """Setting that is neither 'auto', 'disable', nor a valid IP literal raises."""
    with pytest.raises(ValueError, match="invalid webrtc_ip"):
        resolve_webrtc_ip("not-an-ip", proxy=None)


def test_launch_args_contain_webrtc_flag_for_patched():
    """PatchedEngine.build_args() must include --fingerprint-webrtc-ip=<setting>
    when webrtc_ip_flag is set on the engine instance."""
    from tellurium.browser.engine import PatchedEngine
    from tellurium.stealth.profile import StealthProfile

    engine = PatchedEngine(
        executable="/fake/tellurium-chromium",
        webrtc_ip_flag="198.51.100.7",
    )
    profile = StealthProfile.from_seed(42)
    args = engine.build_args(profile)
    assert any(a == "--fingerprint-webrtc-ip=198.51.100.7" for a in args), (
        f"Expected webrtc flag in args, got: {args}"
    )


def test_launch_args_omit_webrtc_flag_for_stock():
    """StockEngine must NOT emit --fingerprint-webrtc-ip= (unknown flag)."""
    from tellurium.browser.engine import StockEngine
    from tellurium.stealth.profile import StealthProfile

    engine = StockEngine(executable="/usr/bin/google-chrome")
    profile = StealthProfile.from_seed(42)
    args = engine.build_args(profile)
    assert not any("fingerprint-webrtc-ip" in a for a in args)


def test_webrtc_js_anchored_to_candidate_lines():
    """Regression: regex must anchor to a=candidate lines, not match random IPs
    embedded elsewhere in SDP."""
    from pathlib import Path

    js_path = (
        Path(__file__).parent.parent.parent / "tellurium" / "stealth" / "scripts" / "webrtc.js"
    )
    content = js_path.read_text()
    assert "^(a=candidate:" in content, (
        "webrtc.js regex must anchor on a=candidate line start to prevent "
        "false-positive IP rewrites on debug/extension SDP lines"
    )
    assert "new RTCSessionDescription" not in content, (
        "webrtc.js must not rely on RTCSessionDescription constructor "
        "(undefined in some isolated worlds)"
    )


# ---------------------------------------------------------------------------
# Browser.launch(browser="patched") -> --fingerprint-webrtc-ip value
# ---------------------------------------------------------------------------


def _patched_engine_args(monkeypatch, **launch_kwargs) -> list[str]:
    """Run launch() with the patched engine up to flag assembly; return its args."""
    import asyncio

    from tellurium.browser import browser as browser_mod
    from tellurium.browser.engine import PatchedEngine

    captured: list[str] = []
    real_build_args = PatchedEngine.build_args

    def spy_build_args(self, profile):
        args = real_build_args(self, profile)
        captured.extend(args)
        return args

    async def fake_exec(self):
        return "/bin/true"

    def stop(**_kw):
        raise RuntimeError("stop-here")

    monkeypatch.setattr(PatchedEngine, "build_args", spy_build_args)
    monkeypatch.setattr(PatchedEngine, "get_executable", fake_exec)
    monkeypatch.setattr("tellurium.browser.launch_plan.build_chrome_flags", stop)
    with pytest.raises(RuntimeError, match="stop-here"):
        asyncio.run(browser_mod.Browser.launch(browser="patched", headless=True, **launch_kwargs))
    return captured


def test_patched_auto_passes_the_resolved_proxy_ip(monkeypatch):
    args = _patched_engine_args(
        monkeypatch, webrtc_ip="auto", proxy="http://127.0.0.1:8080", seed=1
    )
    assert "--fingerprint-webrtc-ip=127.0.0.1" in args


def test_patched_explicit_ip_is_passed_through(monkeypatch):
    args = _patched_engine_args(monkeypatch, webrtc_ip="198.51.100.7", seed=1)
    assert "--fingerprint-webrtc-ip=198.51.100.7" in args


def test_patched_disable_leaves_the_native_default(monkeypatch):
    """'disable' means no spoofing: the native patch keeps its default
    (drop srflx/relay, seeded mDNS) instead of dropping every candidate."""
    args = _patched_engine_args(monkeypatch, webrtc_ip="disable", seed=1)
    assert not any(a.startswith("--fingerprint-webrtc-ip") for a in args)

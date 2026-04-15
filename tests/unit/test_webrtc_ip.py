"""Tests for WebRTC IP resolution pipeline (review 2026-04-15 #9)."""
import pytest
from unittest.mock import patch
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
        lambda host: "198.51.100.7" if host == "proxy.example.com" else (_ for _ in ()).throw(OSError),
    )
    ip = resolve_webrtc_ip("auto", proxy="http://proxy.example.com:8080")
    assert ip == "198.51.100.7"


def test_resolve_webrtc_ip_auto_without_proxy_raises():
    """'auto' without a proxy is a misconfiguration — raise ValueError."""
    with pytest.raises(ValueError, match="webrtc_ip='auto' requires proxy="):
        resolve_webrtc_ip("auto", proxy=None)


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

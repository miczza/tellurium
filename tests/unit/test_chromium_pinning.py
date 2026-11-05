import hashlib

import pytest

from tellurium.browser._cache import BINARY_NAME
from tellurium.browser.engine import PatchedEngine


def test_pinned_version_uses_specific_dir(tmp_path):
    """PatchedEngine(chromium_version='146.0.7680.188') resolves to
    ~/.tellurium/chromium/146.0.7680.188/, not current/."""
    cache_root = tmp_path / ".tellurium" / "chromium"
    pinned = cache_root / "146.0.7680.188"
    pinned.mkdir(parents=True)
    (pinned / BINARY_NAME).write_text("binary")

    eng = PatchedEngine(
        cache_root=cache_root,
        chromium_version="146.0.7680.188",
    )
    resolved = eng.resolve_binary_path()
    assert resolved == pinned / BINARY_NAME


def test_pinned_version_bypasses_update_check(tmp_path, monkeypatch):
    """Pinned version must not trigger the daily update check."""
    called = []

    def fake_check(*a, **kw):
        called.append(True)

    monkeypatch.setattr("tellurium.browser._update_check.check_for_update", fake_check)
    cache_root = tmp_path / ".tellurium" / "chromium"
    pinned = cache_root / "146.0.7680.188"
    pinned.mkdir(parents=True)
    (pinned / BINARY_NAME).write_text("binary")

    eng = PatchedEngine(
        cache_root=cache_root,
        chromium_version="146.0.7680.188",
    )
    eng.resolve_binary_path()
    assert called == [], "Pinned version must not trigger update check"


def test_pinned_sha256_verified(tmp_path):
    """chromium_sha256 must be verified before returning the path."""
    cache_root = tmp_path / ".tellurium" / "chromium"
    pinned = cache_root / "146.0.7680.188"
    pinned.mkdir(parents=True)
    binary = pinned / BINARY_NAME
    binary.write_bytes(b"binary-content")
    expected_sha = hashlib.sha256(b"binary-content").hexdigest()

    from tellurium.browser.engine import BinaryCorruptedError

    eng = PatchedEngine(
        cache_root=cache_root,
        chromium_version="146.0.7680.188",
        chromium_sha256="00" * 32,
    )
    with pytest.raises(BinaryCorruptedError, match=r"SHA256 mismatch"):
        eng.resolve_binary_path()

    eng2 = PatchedEngine(
        cache_root=cache_root,
        chromium_version="146.0.7680.188",
        chromium_sha256=expected_sha,
    )
    assert eng2.resolve_binary_path() == binary


def test_auto_security_update_installs_security_release(tmp_path, monkeypatch):
    """auto_security_update=True downloads a security release when the daily
    check reports one; non-security releases are only warned about."""
    from tellurium.browser._update_check import UpdateInfo

    cache_root = tmp_path / ".tellurium" / "chromium"
    cur = cache_root / "146.0.7680.180"
    cur.mkdir(parents=True)
    (cur / BINARY_NAME).write_text("binary")
    from tellurium.browser import _cache

    _cache.set_current("146.0.7680.180", cache_root)

    info = UpdateInfo(
        installed="146.0.7680.180",
        latest="146.0.7680.195",
        manifest={"security": True, "cve": ["CVE-2026-1"]},
    )
    monkeypatch.setattr("tellurium.browser._update_check.check_for_update", lambda **kw: info)
    downloaded = []
    monkeypatch.setattr(
        "tellurium.browser._patched_download.download_patched",
        lambda v, **kw: downloaded.append(v),
    )
    PatchedEngine(cache_root=cache_root, auto_security_update=True).resolve_binary_path()
    assert downloaded == ["146.0.7680.195"]

    downloaded.clear()
    PatchedEngine(cache_root=cache_root, auto_security_update=False).resolve_binary_path()
    assert downloaded == []


@pytest.mark.parametrize("error", [TimeoutError("read timed out"), ConnectionResetError()])
def test_auto_security_update_network_error_falls_back_to_installed(tmp_path, monkeypatch, error):
    """A security download that dies on the network leaves the installed
    binary in use: the launch goes on, the failure is only logged."""
    from tellurium.browser import _cache
    from tellurium.browser._update_check import UpdateInfo

    cache_root = tmp_path / ".tellurium" / "chromium"
    cur = cache_root / "146.0.7680.180"
    cur.mkdir(parents=True)
    (cur / BINARY_NAME).write_text("binary")
    _cache.set_current("146.0.7680.180", cache_root)
    info = UpdateInfo(
        installed="146.0.7680.180",
        latest="146.0.7680.195",
        manifest={"security": True, "cve": []},
    )
    monkeypatch.setattr("tellurium.browser._update_check.check_for_update", lambda **kw: info)

    def broken(v, **kw):
        raise error

    monkeypatch.setattr("tellurium.browser._patched_download.download_patched", broken)
    eng = PatchedEngine(cache_root=cache_root, auto_security_update=True)
    assert eng.resolve_binary_path() == cur / BINARY_NAME


def test_legacy_binary_name_still_resolves(tmp_path):
    """Installs done with the v0.1.0 README (binary named tellurium-chromium) keep working."""
    cache_root = tmp_path / ".tellurium" / "chromium"
    pinned = cache_root / "146.0.7680.188"
    pinned.mkdir(parents=True)
    (pinned / "tellurium-chromium").write_text("binary")
    eng = PatchedEngine(cache_root=cache_root, chromium_version="146.0.7680.188")
    assert eng.resolve_binary_path() == pinned / "tellurium-chromium"


def test_unpinned_without_current_symlink_uses_newest(tmp_path, monkeypatch):
    monkeypatch.setattr("tellurium.browser._update_check.check_for_update", lambda **kw: None)
    cache_root = tmp_path / ".tellurium" / "chromium"
    for v in ("146.0.7680.188", "147.0.7700.1"):
        d = cache_root / v
        d.mkdir(parents=True)
        (d / BINARY_NAME).write_text("binary")
    eng = PatchedEngine(cache_root=cache_root)
    assert eng.resolve_binary_path() == cache_root / "147.0.7700.1" / BINARY_NAME

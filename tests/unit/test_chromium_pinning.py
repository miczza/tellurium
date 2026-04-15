import pytest
from pathlib import Path
from tellurium.browser.engine import PatchedEngine


def test_pinned_version_uses_specific_dir(tmp_path):
    """PatchedEngine(chromium_version='146.0.7680.188') resolves to
    ~/.tellurium/chromium/146.0.7680.188/, not current/."""
    cache_root = tmp_path / ".tellurium" / "chromium"
    pinned = cache_root / "146.0.7680.188"
    pinned.mkdir(parents=True)
    (pinned / "tellurium-chromium").write_text("binary")

    eng = PatchedEngine(
        cache_root=cache_root,
        chromium_version="146.0.7680.188",
    )
    resolved = eng.resolve_binary_path()
    assert resolved == pinned / "tellurium-chromium"


def test_pinned_version_bypasses_update_check(tmp_path, monkeypatch):
    """Pinned version must not trigger the daily update check."""
    called = []

    def fake_check(*a, **kw):
        called.append(True)

    monkeypatch.setattr(
        "tellurium.browser._update_check.check_for_update", fake_check
    )
    cache_root = tmp_path / ".tellurium" / "chromium"
    pinned = cache_root / "146.0.7680.188"
    pinned.mkdir(parents=True)
    (pinned / "tellurium-chromium").write_text("binary")

    eng = PatchedEngine(
        cache_root=cache_root,
        chromium_version="146.0.7680.188",
    )
    eng.resolve_binary_path()
    assert called == [], "Pinned version must not trigger update check"


def test_pinned_sha256_verified(tmp_path):
    """chromium_sha256 must be verified before returning the path."""
    import hashlib
    cache_root = tmp_path / ".tellurium" / "chromium"
    pinned = cache_root / "146.0.7680.188"
    pinned.mkdir(parents=True)
    binary = pinned / "tellurium-chromium"
    binary.write_bytes(b"binary-content")
    expected_sha = hashlib.sha256(b"binary-content").hexdigest()

    from tellurium.browser.engine import BinaryCorruptedError
    eng = PatchedEngine(
        cache_root=cache_root,
        chromium_version="146.0.7680.188",
        chromium_sha256="00" * 32,
    )
    with pytest.raises(BinaryCorruptedError):
        eng.resolve_binary_path()

    eng2 = PatchedEngine(
        cache_root=cache_root,
        chromium_version="146.0.7680.188",
        chromium_sha256=expected_sha,
    )
    assert eng2.resolve_binary_path() == binary

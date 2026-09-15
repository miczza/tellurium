import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from tellurium.browser import _update_check


def _fake_urlopen(manifest: dict):
    resp = MagicMock()
    resp.read.return_value = json.dumps(manifest).encode()
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda *a: None
    return lambda url, *a, **kw: resp


def test_update_check_skipped_within_24h(tmp_path, monkeypatch):
    """If last check < 24h ago, no HTTP request is made."""
    cache_root = tmp_path / ".tellurium" / "chromium"
    cache_root.mkdir(parents=True)
    check_file = tmp_path / ".tellurium" / ".update-check"
    now_iso = datetime.now(timezone.utc).isoformat()
    check_file.parent.mkdir(parents=True, exist_ok=True)
    check_file.write_text(json.dumps({"last_check": now_iso, "latest_version": "146.0.7680.188"}))

    called = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: called.append(True))

    _update_check.check_for_update(cache_root=cache_root, check_file=check_file)
    assert called == []


def test_update_check_warns_if_stale(tmp_path, monkeypatch, caplog):
    """If installed version is behind latest, emit WARNING with 'weeks old'."""
    cache_root = tmp_path / ".tellurium" / "chromium"
    old_dir = cache_root / "140.0.7000.0"
    old_dir.mkdir(parents=True)
    (cache_root / "current").symlink_to(old_dir)

    check_file = tmp_path / ".update-check"
    old_iso = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    check_file.write_text(json.dumps({"last_check": old_iso, "latest_version": ""}))

    manifest = {
        "version": "0.1.0", "chromium_upstream": "146.0.7680.188",
        "released_at": (datetime.now(timezone.utc) - timedelta(weeks=2)).isoformat(),
        "security": False,
    }
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(manifest))

    with caplog.at_level(logging.WARNING, logger="tellurium"):
        _update_check.check_for_update(cache_root=cache_root, check_file=check_file)
    assert any("weeks old" in r.message for r in caplog.records)


def test_update_check_warns_aggressively_on_security(tmp_path, monkeypatch, caplog):
    """If manifest.security == true, WARNING includes 'security' and CVE list."""
    cache_root = tmp_path / ".tellurium" / "chromium"
    old_dir = cache_root / "146.0.7680.180"
    old_dir.mkdir(parents=True)
    (cache_root / "current").symlink_to(old_dir)

    check_file = tmp_path / ".update-check"
    old_iso = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    check_file.write_text(json.dumps({"last_check": old_iso, "latest_version": ""}))

    manifest = {
        "version": "0.1.1", "chromium_upstream": "146.0.7680.195",
        "released_at": datetime.now(timezone.utc).isoformat(),
        "security": True,
        "cve": ["CVE-2026-1234"],
        "severity": "high",
    }
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(manifest))

    with caplog.at_level(logging.WARNING, logger="tellurium"):
        _update_check.check_for_update(cache_root=cache_root, check_file=check_file)
    messages = "\n".join(r.message for r in caplog.records)
    assert "security" in messages.lower()
    assert "CVE-2026-1234" in messages


def test_update_check_returns_info_and_url_points_to_chromium_telluride(tmp_path, monkeypatch):
    cache_root = tmp_path / ".tellurium" / "chromium"
    d = cache_root / "146.0.7680.188"
    d.mkdir(parents=True)
    (cache_root / "current").symlink_to(d)
    check_file = tmp_path / ".update-check"
    seen = []

    def urlopen(url, *a, **kw):
        seen.append(url)
        return _fake_urlopen({"version": "0.1.0", "chromium_upstream": "146.0.7680.188"})(url)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    info = _update_check.check_for_update(cache_root=cache_root, check_file=check_file)
    assert info is not None and not info.available
    assert info.installed == "146.0.7680.188"
    assert seen == [_update_check.MANIFEST_URL]
    assert "miczza/chromium-telluride" in _update_check.MANIFEST_URL

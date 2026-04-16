"""Tests for browser management CLI commands."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from tellurium.cli import main


def test_cli_list_browsers_no_browsers(capsys, tmp_path):
    """list-browsers with empty cache shows helpful message."""
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "list-browsers"]):
            main()
    output = capsys.readouterr().out
    assert "No browsers installed" in output or "none" in output.lower()


def test_cli_list_browsers_shows_installed(capsys, tmp_path):
    """list-browsers shows installed versions with metadata."""
    # Create fake installed browser
    browser_dir = tmp_path / "chromium-patched-146.0.7680.188"
    browser_dir.mkdir()
    (browser_dir / "chrome").touch()
    (browser_dir / "MANIFEST.json").write_text('{"version": "146.0.7680.188"}')

    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "list-browsers"]):
            main()
    output = capsys.readouterr().out
    assert "146.0.7680.188" in output


def test_cli_update_browser_check_dry_run(capsys):
    """update-browser --check shows available update without installing."""
    with patch("tellurium.cli._check_latest_patched", return_value="147.0.7700.100"):
        with patch("tellurium.cli._get_installed_version", return_value="146.0.7680.188"):
            with patch("sys.argv", ["tellurium", "update-browser", "--check"]):
                main()
    output = capsys.readouterr().out
    assert "147.0.7700.100" in output
    assert "available" in output.lower()


def test_cli_prune_browsers_keeps_n(capsys, tmp_path):
    """prune-browsers --keep N removes old versions, keeps N newest."""
    # Create 3 fake versions
    for v in ["145.0.7600.100", "146.0.7680.188", "147.0.7700.100"]:
        d = tmp_path / f"chromium-patched-{v}"
        d.mkdir()
        (d / "chrome").touch()

    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "prune-browsers", "--keep", "2"]):
            main()

    output = capsys.readouterr().out
    assert "145.0.7600.100" in output  # removed
    # Verify 2 remain
    remaining = list(tmp_path.glob("chromium-patched-*"))
    assert len(remaining) == 2


def test_cli_verify_browser_success(capsys, tmp_path):
    """verify-browser with valid SHA256 reports success."""
    browser_dir = tmp_path / "chromium-patched-146.0.7680.188"
    browser_dir.mkdir()
    chrome = browser_dir / "chrome"
    chrome.write_bytes(b"fake chrome binary")
    manifest = browser_dir / "MANIFEST.json"

    import hashlib
    expected_hash = hashlib.sha256(b"fake chrome binary").hexdigest()
    manifest.write_text(f'{{"version": "146.0.7680.188", "sha256": "{expected_hash}"}}')

    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "verify-browser"]):
            main()

    output = capsys.readouterr().out
    assert "OK" in output.upper() or "valid" in output.lower()


def test_cli_verify_browser_mismatch(capsys, tmp_path):
    """verify-browser with hash mismatch reports error."""
    browser_dir = tmp_path / "chromium-patched-146.0.7680.188"
    browser_dir.mkdir()
    chrome = browser_dir / "chrome"
    chrome.write_bytes(b"corrupted binary")
    manifest = browser_dir / "MANIFEST.json"
    manifest.write_text('{"version": "146.0.7680.188", "sha256": "0000000000000000000000000000000000000000000000000000000000000000"}')

    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "verify-browser"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0

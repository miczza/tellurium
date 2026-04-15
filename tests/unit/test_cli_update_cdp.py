"""Tests for `tellurium update-cdp` CLI command."""
import json
from unittest.mock import MagicMock, patch
import pytest
from tellurium import cli


def _minimal_protocol() -> dict:
    """Valid-enough protocol.json for CDPGenerator to produce the 11
    bundled domains without erroring."""
    return {
        "version": {"major": "1", "minor": "3"},
        "domains": [
            {"domain": d, "types": [], "commands": [], "events": []}
            for d in ["Target", "Browser", "Page", "Network", "DOM",
                      "Runtime", "Input", "Fetch", "Storage", "Emulation", "Log"]
        ],
    }


def test_update_cdp_without_version_uses_bundled(tmp_path, monkeypatch, capsys):
    """Without --chrome-version: read bundled protocol.json, regenerate domains."""
    protocol_path = tmp_path / "protocol.json"
    domains_dir = tmp_path / "domains"
    domains_dir.mkdir()
    protocol_path.write_text(json.dumps(_minimal_protocol()))

    monkeypatch.setattr(cli, "_protocol_path", lambda: protocol_path)
    monkeypatch.setattr(cli, "_domains_dir", lambda: domains_dir)

    cli._update_cdp(None)

    out = capsys.readouterr().out
    assert "11 CDP domains regenerated" in out
    assert "Downloaded" not in out
    # Verify domains were written
    assert (domains_dir / "page.py").exists()
    assert (domains_dir / "target.py").exists()


def test_update_cdp_with_version_downloads(tmp_path, monkeypatch, capsys):
    """With --chrome-version 146: download protocol.json from upstream, regenerate."""
    protocol_path = tmp_path / "protocol.json"
    domains_dir = tmp_path / "domains"
    domains_dir.mkdir()
    protocol_bytes = json.dumps(_minimal_protocol()).encode()

    monkeypatch.setattr(cli, "_protocol_path", lambda: protocol_path)
    monkeypatch.setattr(cli, "_domains_dir", lambda: domains_dir)

    # Mock urlopen to return fake response
    fake_response = MagicMock()
    fake_response.read.return_value = protocol_bytes
    fake_response.__enter__ = lambda self: self
    fake_response.__exit__ = lambda *a: None

    captured_urls: list[str] = []

    def fake_urlopen(url, *a, **kw):
        captured_urls.append(url)
        return fake_response

    with patch("urllib.request.urlopen", fake_urlopen):
        cli._update_cdp("146")

    assert any("146" in u for u in captured_urls), (
        f"Expected Chrome 146 in download URL, got: {captured_urls}"
    )
    assert any("ChromeDevTools/devtools-protocol" in u for u in captured_urls), (
        f"Expected devtools-protocol repo in URL, got: {captured_urls}"
    )
    out = capsys.readouterr().out
    assert "Downloaded protocol.json for Chrome 146" in out
    assert "11 CDP domains regenerated" in out
    # Verify protocol file was written
    assert protocol_path.exists()
    assert protocol_path.read_bytes() == protocol_bytes

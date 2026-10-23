"""Tests for browser management CLI commands (shared cache layout in _cache)."""

import hashlib
import json
from unittest.mock import patch

import pytest

from tellurium.browser import _cache
from tellurium.browser._manifest import current_platform
from tellurium.cli import main


def _install(
    tmp_path, version, binary=b"fake chrome binary", sha=None, manifest=True, current=False
):
    d = tmp_path / version
    d.mkdir(parents=True)
    (d / "chrome").write_bytes(binary)
    if manifest:
        data = {
            "version": "0.1.0",
            "chromium_upstream": version,
            "binary_sha256": {current_platform(): sha or hashlib.sha256(binary).hexdigest()},
        }
        (d / "MANIFEST.json").write_text(json.dumps(data))
    if current:
        _cache.set_current(version, tmp_path)
    return d


def test_cli_list_browsers_no_browsers(capsys, tmp_path):
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "list-browsers"]):
            main()
    assert "No browsers installed" in capsys.readouterr().out


def test_cli_list_browsers_shows_installed(capsys, tmp_path):
    _install(tmp_path, "146.0.7680.188", current=True)
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "list-browsers"]):
            main()
    out = capsys.readouterr().out
    assert "146.0.7680.188" in out
    assert "(current)" in out
    assert "SHA256:" in out


def test_cli_info_sees_cache_layout(capsys, tmp_path):
    """info must find a browser installed in the engine's layout (regression:
    cli and engine used to disagree on the cache path)."""
    _install(tmp_path, "146.0.7680.188", current=True)
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "info"]):
            main()
    out = capsys.readouterr().out
    assert "Browser patched: " in out and "146.0.7680.188" in out
    assert "not installed" not in out


def test_cli_update_browser_check_dry_run(capsys, tmp_path):
    from tellurium.browser._update_check import UpdateInfo

    info = UpdateInfo(
        installed="146.0.7680.188",
        latest="147.0.7700.100",
        manifest={"chromium_upstream": "147.0.7700.100"},
    )
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("tellurium.cli._get_installed_version", return_value="146.0.7680.188"):
            with patch("tellurium.browser._update_check.check_for_update", return_value=info):
                with patch("sys.argv", ["tellurium", "update-browser", "--check"]):
                    main()
    out = capsys.readouterr().out
    assert "147.0.7700.100" in out
    assert "available" in out.lower()


def test_cli_update_browser_installs(capsys, tmp_path):
    from tellurium.browser._update_check import UpdateInfo

    info = UpdateInfo(
        installed="146.0.7680.188",
        latest="147.0.7700.100",
        manifest={"chromium_upstream": "147.0.7700.100"},
    )
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("tellurium.cli._get_installed_version", return_value="146.0.7680.188"):
            with patch("tellurium.browser._update_check.check_for_update", return_value=info):
                with patch("tellurium.cli._install_patched", return_value=True) as inst:
                    with patch("sys.argv", ["tellurium", "update-browser"]):
                        main()
    inst.assert_called_once_with("147.0.7700.100", allow_unverified=False)


def test_cli_update_browser_allow_unverified(tmp_path):
    from tellurium.browser._update_check import UpdateInfo

    info = UpdateInfo(installed=None, latest="147.0.7700.100", manifest={})
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("tellurium.cli._get_installed_version", return_value=None):
            with patch("tellurium.browser._update_check.check_for_update", return_value=info):
                with patch("tellurium.cli._install_patched", return_value=True) as inst:
                    argv = ["tellurium", "update-browser", "--allow-unverified"]
                    with patch("sys.argv", argv):
                        main()
    inst.assert_called_once_with("147.0.7700.100", allow_unverified=True)


def test_cli_verify_browser_reinstall_allow_unverified(tmp_path):
    from tellurium.browser import _patched_download

    _install(tmp_path, "146.0.7680.188", sha="00" * 32)
    entry = _cache.InstalledBrowser(
        version="146.0.7680.188",
        path=tmp_path,
        binary=tmp_path / "chrome",
        manifest=None,
        is_current=True,
    )
    argv = ["tellurium", "verify-browser", "--reinstall", "--allow-unverified"]
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch.object(_patched_download, "reinstall", return_value=entry) as re:
            with patch("sys.argv", argv):
                main()
    assert re.call_args.kwargs["allow_unverified"] is True


def test_cli_update_browser_security_only_skips_non_security(capsys, tmp_path):
    from tellurium.browser._update_check import UpdateInfo

    info = UpdateInfo(
        installed="146.0.7680.188",
        latest="147.0.7700.100",
        manifest={"chromium_upstream": "147.0.7700.100", "security": False},
    )
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("tellurium.cli._get_installed_version", return_value="146.0.7680.188"):
            with patch("tellurium.browser._update_check.check_for_update", return_value=info):
                with patch("tellurium.cli._install_patched") as inst:
                    with patch("sys.argv", ["tellurium", "update-browser", "--security-only"]):
                        main()
    inst.assert_not_called()
    assert "security" in capsys.readouterr().out.lower()


def test_cli_prune_browsers_keeps_n_and_current(capsys, tmp_path):
    for v in ["145.0.7600.100", "146.0.7680.188", "147.0.7700.100", "148.0.7800.1"]:
        _install(tmp_path, v)
    _cache.set_current("145.0.7600.100", tmp_path)  # oldest is current: must survive

    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "prune-browsers", "--keep", "2"]):
            main()

    remaining = sorted(b.version for b in _cache.installed_browsers(tmp_path))
    assert remaining == ["145.0.7600.100", "147.0.7700.100", "148.0.7800.1"]
    assert "146.0.7680.188" in capsys.readouterr().out


def test_cli_verify_browser_success(capsys, tmp_path):
    _install(tmp_path, "146.0.7680.188")
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "verify-browser"]):
            main()
    assert "OK" in capsys.readouterr().out


def test_cli_verify_browser_mismatch(capsys, tmp_path):
    _install(tmp_path, "146.0.7680.188", sha="00" * 32)
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "verify-browser"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
    assert exc_info.value.code != 0
    assert "CORRUPT" in capsys.readouterr().out


def test_cli_verify_browser_reinstall_calls_download(capsys, tmp_path):
    _install(tmp_path, "146.0.7680.188", sha="00" * 32)
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("tellurium.cli._install_patched", return_value=True) as inst:
            with patch("sys.argv", ["tellurium", "verify-browser", "--reinstall"]):
                main()  # reinstall succeeded -> exit 0
    inst.assert_called_once_with("146.0.7680.188", reinstall=True, allow_unverified=False)


def test_cli_download_browser_patched_calls_installer(tmp_path):
    with patch("tellurium.cli._install_patched", return_value=True) as inst:
        with patch(
            "sys.argv",
            [
                "tellurium",
                "download-browser",
                "--browser",
                "patched",
                "--version",
                "146.0.7680.188",
            ],
        ):
            main()
    inst.assert_called_once_with("146.0.7680.188", allow_unverified=False)


@pytest.mark.parametrize("flag", [[], ["--allow-unverified"]])
def test_cli_download_browser_allow_unverified_reaches_the_installer(tmp_path, flag):
    from tellurium.browser import _patched_download

    entry = _cache.InstalledBrowser(
        version="146.0.7680.188",
        path=tmp_path,
        binary=tmp_path / "chrome",
        manifest=None,
        is_current=True,
    )
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch.object(_patched_download, "download_patched", return_value=entry) as dl:
            argv = ["tellurium", "download-browser", "--browser", "patched", *flag]
            with patch("sys.argv", argv):
                main()
    assert dl.call_args.kwargs["allow_unverified"] is bool(flag)


def test_cli_prune_browsers_removes_orphaned_old_installs(tmp_path):
    _install(tmp_path, "146.0.7680.188", current=True)
    orphan = tmp_path / ".old-146.0.7680.188-deadbeef"
    orphan.mkdir()
    with patch("tellurium.cli._cache_dir", return_value=tmp_path):
        with patch("sys.argv", ["tellurium", "prune-browsers"]):
            main()
    assert not orphan.exists()
    assert (tmp_path / "146.0.7680.188" / "chrome").is_file()

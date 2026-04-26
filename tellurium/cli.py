"""Tellurium CLI."""
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path


def _cache_dir() -> Path:
    """Return the Tellurium cache directory."""
    return Path.home() / ".tellurium"


def _get_installed_version(cache: Path) -> str | None:
    """Return the installed patched browser version, or None if not installed."""
    for d in sorted(cache.glob("chromium-patched-*"), reverse=True):
        if (d / "chrome").exists():
            return d.name.replace("chromium-patched-", "")
    return None


def _check_latest_patched() -> str | None:
    """Check GitHub releases for latest patched browser version."""
    import urllib.request
    import json
    try:
        url = "https://api.github.com/repos/miczza/tellurium-chromium/releases/latest"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("tag_name", "").lstrip("v")
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(
        prog="tellurium",
        description="Tellurium automates browsers. Quietly.",
    )
    sub = parser.add_subparsers(dest="command")

    # update-cdp
    cdp_parser = sub.add_parser("update-cdp", help="Regenerate CDP bindings")
    cdp_parser.add_argument("--chrome-version", help="Target Chrome version")

    # download-browser
    dl_parser = sub.add_parser("download-browser", help="Download browser binary")
    dl_parser.add_argument("--browser", default="stock", choices=["stock", "patched"],
                           help="Browser type to download")

    # stealth-test
    st_parser = sub.add_parser("stealth-test", help="Test stealth against detection sites")
    st_parser.add_argument("--browser", default="stock", choices=["stock", "patched"])
    st_parser.add_argument("--full", action="store_true", help="Run full test suite")

    # info
    sub.add_parser("info", help="Show Tellurium info")

    # list-browsers
    sub.add_parser("list-browsers", help="List installed browser versions")

    # update-browser
    upd_parser = sub.add_parser("update-browser", help="Check for/install browser updates")
    upd_parser.add_argument("--check", action="store_true", help="Check only, don't install")
    upd_parser.add_argument("--security-only", action="store_true", help="Only security updates")

    # prune-browsers
    prune_parser = sub.add_parser("prune-browsers", help="Remove old browser versions")
    prune_parser.add_argument("--keep", type=int, default=2, help="Keep N most recent versions")

    # verify-browser
    verify_parser = sub.add_parser("verify-browser", help="Verify browser binary integrity")
    verify_parser.add_argument("--reinstall", action="store_true", help="Reinstall if corrupt")

    args = parser.parse_args()

    if args.command == "update-cdp":
        _update_cdp(args.chrome_version)
    elif args.command == "download-browser":
        asyncio.run(_download_browser(args.browser))
    elif args.command == "stealth-test":
        asyncio.run(_stealth_test(args.browser, args.full))
    elif args.command == "info":
        _show_info()
    elif args.command == "list-browsers":
        _list_browsers()
    elif args.command == "update-browser":
        _update_browser(args.check, args.security_only)
    elif args.command == "prune-browsers":
        _prune_browsers(args.keep)
    elif args.command == "verify-browser":
        _verify_browser(args.reinstall)
    else:
        parser.print_help()


def _protocol_path():
    from pathlib import Path
    return Path(__file__).parent / "cdp" / "protocol.json"


def _domains_dir():
    from pathlib import Path
    return Path(__file__).parent / "cdp" / "domains"


def _update_cdp(chrome_version: str | None) -> None:
    """Regenerate CDP bindings.

    Without chrome_version: use the bundled protocol.json.
    With chrome_version: download protocol.json from the
    ChromeDevTools/devtools-protocol repo at tag v{chrome_version},
    overwrite the bundled file, then regenerate.
    """
    import json
    import urllib.request
    from tellurium.cdp.generator import CDPGenerator

    protocol_path = _protocol_path()
    domains_dir = _domains_dir()

    if chrome_version:
        url = (
            f"https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/"
            f"v{chrome_version}/json/browser_protocol.json"
        )
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(
                    f"Error: Chrome version {chrome_version} not found at "
                    f"ChromeDevTools/devtools-protocol (404). Check available "
                    f"tags: https://github.com/ChromeDevTools/devtools-protocol/tags",
                    file=sys.stderr,
                )
            else:
                print(f"Error: HTTP {e.code} fetching protocol: {e}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f"Error: network failure fetching protocol: {e.reason}", file=sys.stderr)
            sys.exit(1)
        protocol_path.write_bytes(data)
        print(f"  Downloaded protocol.json for Chrome {chrome_version}")

    if not protocol_path.exists():
        print("Error: protocol.json not found", file=sys.stderr)
        sys.exit(1)

    with open(protocol_path) as f:
        protocol = json.load(f)

    gen = CDPGenerator(protocol)
    modules = gen.generate_all_bundled()

    for name, source in modules.items():
        path = domains_dir / f"{name}.py"
        path.write_text(source)
        print(f"  Generated: {path.name}")

    print(f"\n{len(modules)} CDP domains regenerated.")


async def _download_browser(browser_type: str) -> None:
    """Download a browser binary."""
    if browser_type == "stock":
        from tellurium.browser.launcher import download_cft
        path = await download_cft()
        print(f"Chrome for Testing downloaded: {path}")
    elif browser_type == "patched":
        print("tellurium-chromium download not yet available.")
        print("Binary will be available via GitHub Releases when the patched Chromium is built.")


async def _stealth_test(browser_type: str, full: bool) -> None:
    """Run stealth tests against detection sites."""
    from tellurium import Browser

    print("Running stealth tests...\n")

    tests = [
        ("navigator.webdriver", "navigator.webdriver"),
        ("window.chrome", "typeof window.chrome === 'object'"),
        ("navigator.plugins", "navigator.plugins.length > 0"),
    ]

    if full:
        tests.extend([
            ("WebGL renderer", "(() => { const c = document.createElement('canvas'); const gl = c.getContext('webgl'); if (!gl) return false; const ext = gl.getExtension('WEBGL_debug_renderer_info'); return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : false; })()"),
        ])

    async with Browser.launch(headless=True, stealth=True, browser=browser_type) as browser:
        tab = await browser.new_tab("about:blank")

        for name, expr in tests:
            try:
                result = await tab.eval(expr)
                if name == "navigator.webdriver":
                    passed = result is None or result is False
                else:
                    passed = bool(result)
                status = "PASS" if passed else "FAIL"
                print(f"  {name:<30} {status}  ({result})")
            except Exception as e:
                print(f"  {name:<30} ERROR ({e})")

    print("\nDone.")


def _show_info() -> None:
    """Show Tellurium installation info."""
    import shutil
    from pathlib import Path

    print("Tellurium 0.1.0\n")

    # Stock browser
    from tellurium.browser.launcher import _find_chrome_candidates
    candidates = _find_chrome_candidates()
    if candidates:
        path, kind = candidates[0]
        print(f"  Browser stock:   {path} ({kind})")
    else:
        print("  Browser stock:   not found")

    # Patched browser
    patched = Path.home() / ".tellurium" / "chromium-patched-146.0.7680.188" / "chrome"
    if patched.exists():
        print(f"  Browser patched: {patched}")
    else:
        print("  Browser patched: not installed")

    # CDP bindings
    protocol = Path(__file__).parent / "cdp" / "protocol.json"
    if protocol.exists():
        print(f"  CDP bindings:    bundled")
    else:
        print(f"  CDP bindings:    not found")

    # GeoIP
    try:
        import maxminddb
        print("  GeoIP:           installed (maxminddb)")
    except ImportError:
        print("  GeoIP:           not installed (pip install tellurium[geoip])")

    # Cache dir
    cache = Path.home() / ".tellurium"
    print(f"  Cache:           {cache}")


def _list_browsers() -> None:
    """List installed browser versions."""
    import json
    cache = _cache_dir()
    browsers = sorted(cache.glob("chromium-patched-*"), reverse=True)

    if not browsers:
        print("No browsers installed.")
        return

    print("Installed browsers:\n")
    for browser_dir in browsers:
        version = browser_dir.name.replace("chromium-patched-", "")
        chrome_path = browser_dir / "chrome"
        manifest_path = browser_dir / "MANIFEST.json"

        if not chrome_path.exists():
            continue

        sha256_prefix = ""
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                sha256 = manifest.get("sha256", "")
                if sha256:
                    sha256_prefix = sha256[:16] + "..."
            except Exception:
                pass

        print(f"  {version}")
        print(f"    Path: {browser_dir}")
        if sha256_prefix:
            print(f"    SHA256: {sha256_prefix}")
        print()


def _update_browser(check_only: bool, security_only: bool) -> None:
    """Check for and optionally install browser updates."""
    cache = _cache_dir()
    installed = _get_installed_version(cache)
    latest = _check_latest_patched()

    if not latest:
        print("Could not check for updates (network error or no releases found).")
        return

    if not installed:
        print(f"No patched browser installed.")
        print(f"Latest available: {latest}")
        if not check_only:
            print("\nRun 'tellurium download-browser --browser patched' to install.")
        return

    if installed == latest:
        print(f"Already up to date: {installed}")
        return

    print(f"Installed: {installed}")
    print(f"Available: {latest}")

    if check_only:
        print("\nUpdate available. Run 'tellurium update-browser' to install.")
    else:
        # v0.1.x: implement actual update download — see CHANGELOG.md "Unreleased"
        print(
            "\nAuto-download is experimental and not wired in v0.1.\n"
            "To install the patched binary manually, see README.md\n"
            "  → 'Patched binary (experimental)'.\n"
            "Recommended for v0.1: use stock Chrome via Browser.launch()\n"
            "  without browser='patched'."
        )


def _prune_browsers(keep: int) -> None:
    """Remove old browser versions, keeping the N most recent."""
    import shutil
    cache = _cache_dir()
    browsers = sorted(cache.glob("chromium-patched-*"), reverse=True)

    if len(browsers) <= keep:
        print(f"Only {len(browsers)} browser(s) installed, keeping all.")
        return

    to_remove = browsers[keep:]
    to_keep = browsers[:keep]

    print(f"Keeping {keep} most recent version(s):")
    for b in to_keep:
        version = b.name.replace("chromium-patched-", "")
        print(f"  {version}")

    print(f"\nRemoving {len(to_remove)} old version(s):")
    for browser_dir in to_remove:
        version = browser_dir.name.replace("chromium-patched-", "")
        print(f"  {version}")
        shutil.rmtree(browser_dir)

    print("\nDone.")


def _verify_browser(reinstall: bool) -> None:
    """Verify browser binary integrity using SHA256 from MANIFEST.json."""
    import hashlib
    import json

    cache = _cache_dir()
    browsers = list(cache.glob("chromium-patched-*"))

    if not browsers:
        print("No browsers installed.")
        return

    all_valid = True
    for browser_dir in browsers:
        version = browser_dir.name.replace("chromium-patched-", "")
        chrome_path = browser_dir / "chrome"
        manifest_path = browser_dir / "MANIFEST.json"

        if not chrome_path.exists():
            print(f"  {version}: MISSING (chrome binary not found)")
            all_valid = False
            continue

        if not manifest_path.exists():
            print(f"  {version}: SKIP (no MANIFEST.json)")
            continue

        try:
            manifest = json.loads(manifest_path.read_text())
            expected_hash = manifest.get("sha256")
            if not expected_hash:
                print(f"  {version}: SKIP (no SHA256 in manifest)")
                continue

            actual_hash = hashlib.sha256(chrome_path.read_bytes()).hexdigest()

            if actual_hash == expected_hash:
                print(f"  {version}: OK (SHA256 valid)")
            else:
                print(f"  {version}: CORRUPT (SHA256 mismatch)")
                print(f"    Expected: {expected_hash[:16]}...")
                print(f"    Actual:   {actual_hash[:16]}...")
                all_valid = False

                if reinstall:
                    # v0.1.x: implement reinstall — see CHANGELOG.md "Unreleased"
                    print(
                        f"    --reinstall is not wired in v0.1.\n"
                        f"    Manual fix: remove the corrupt binary at\n"
                        f"      {browser_dir}\n"
                        f"    and re-install via the manual workflow in\n"
                        f"    README.md → 'Patched binary (experimental)'."
                    )
        except Exception as e:
            print(f"  {version}: ERROR ({e})")
            all_valid = False

    if not all_valid:
        sys.exit(1)

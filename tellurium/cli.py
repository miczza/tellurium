"""Tellurium CLI."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from tellurium.browser import _cache


def _cache_dir() -> Path:
    """Return the patched-browser cache root (``~/.tellurium/chromium``)."""
    return _cache.cache_root()


def _get_installed_version(cache: Path) -> str | None:
    """Return the default installed patched version, or None if not installed."""
    return _cache.installed_version(cache)


def _check_latest_patched() -> str | None:
    """Return the chromium version of the latest chromium-telluride release."""
    from tellurium.browser._patched_download import latest_version

    return latest_version()


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
    dl_parser.add_argument(
        "--browser", default="stock", choices=["stock", "patched"], help="Browser type to download"
    )
    dl_parser.add_argument(
        "--version", default=None, help="Chromium version to download (default: latest release)"
    )
    dl_parser.add_argument("--allow-unverified", action="store_true", help="Skip SHA256SUMS")

    # download-geoip
    geo_parser = sub.add_parser(
        "download-geoip", help="Download a GeoIP country database for proxy locale detection"
    )
    geo_parser.add_argument(
        "--maxmind-license-key",
        default=None,
        help="Use MaxMind GeoLite2-Country instead of DB-IP Lite",
    )

    # stealth-test
    st_parser = sub.add_parser("stealth-test", help="Test stealth against detection sites")
    st_parser.add_argument("--browser", default="stock", choices=["stock", "patched"])
    st_parser.add_argument(
        "--full", action="store_true", help="Also visit live detection sites (needs network)"
    )
    st_parser.add_argument("--headed", action="store_true", help="Run with a visible window")

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
        asyncio.run(_download_browser(args.browser, args.version, args.allow_unverified))
    elif args.command == "download-geoip":
        _download_geoip(args.maxmind_license_key)
    elif args.command == "stealth-test":
        asyncio.run(_stealth_test(args.browser, args.full, args.headed))
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
    return Path(__file__).parent / "cdp" / "protocol.json"


def _domains_dir():
    return Path(__file__).parent / "cdp" / "domains"


def _update_cdp(chrome_version: str | None) -> None:
    """Regenerate CDP bindings.

    Without chrome_version: use the bundled protocol.json.
    With chrome_version: download protocol.json from the
    ChromeDevTools/devtools-protocol repo at tag v{chrome_version},
    overwrite the bundled file, then regenerate.
    """
    import json
    import urllib.error
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


# --------------------------------------------------------------------------- #
# Patched browser management
# --------------------------------------------------------------------------- #


def _progress_printer():
    last = [-1]

    def cb(done: int, total: int | None) -> None:
        if total:
            pct = int(done * 100 / total)
            if pct != last[0] and pct % 5 == 0:
                last[0] = pct
                print(f"\r  downloading... {pct:3d}% ({done >> 20} MB)", end="", flush=True)
        else:
            mb = done >> 20
            if mb != last[0]:
                last[0] = mb
                print(f"\r  downloading... {mb} MB", end="", flush=True)

    return cb


def _install_patched(
    version: str | None, *, reinstall: bool = False, allow_unverified: bool = False
) -> bool:
    """Download (or re-download) a patched release; print outcome; return success."""
    from tellurium.browser._patched_download import DownloadError, download_patched
    from tellurium.browser._patched_download import reinstall as _re

    where = {"cache_root": _cache_dir(), "progress": _progress_printer()}
    try:
        if reinstall and version:
            entry = _re(version, **where)
        else:
            entry = download_patched(version, allow_unverified=allow_unverified, **where)
    except DownloadError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return False
    except OSError as e:
        print(f"\nError: network/filesystem failure: {e}", file=sys.stderr)
        return False
    print(f"\nchromium-telluride {entry.version} installed: {entry.binary}")
    if entry.is_current:
        print("  (set as current)")
    return True


async def _download_browser(kind: str, version: str | None, unverified: bool) -> None:
    """Download a browser binary (*unverified*: patched release without SHA256SUMS)."""
    if kind == "stock":
        from tellurium.browser.launcher import download_cft

        path = await download_cft(version or "latest")
        print(f"Chrome for Testing downloaded: {path}")
    elif kind == "patched":
        if not _install_patched(version, allow_unverified=unverified):
            sys.exit(1)


def _download_geoip(license_key: str | None) -> None:
    from tellurium.stealth.geoip import download_geoip_db

    try:
        path = download_geoip_db(maxmind_license_key=license_key)
    except Exception as e:  # noqa: BLE001 - CLI boundary
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"GeoIP database installed: {path}")


async def _stealth_test(browser_type: str, full: bool, headed: bool = False) -> None:
    """Run stealth checks: local invariants, plus live detection sites with --full."""
    from tellurium import Browser

    print(f"Running stealth tests (browser={browser_type})...\n")

    local_tests = [
        ("navigator.webdriver", "navigator.webdriver", lambda r: r is False or r is None),
        ("window.chrome", "typeof window.chrome === 'object'", bool),
        ("navigator.plugins", "navigator.plugins.length > 0", bool),
        (
            "webdriver getter shape",
            "Function.prototype.toString.call(Object.getOwnPropertyDescriptor("
            "Object.getPrototypeOf(navigator),'webdriver').get)",
            lambda r: r == "function get webdriver() { [native code] }",
        ),
        (
            "Function.prototype.toString shape",
            "Function.prototype.toString.call(Function.prototype.toString)",
            lambda r: r == "function toString() { [native code] }",
        ),
    ]

    failures = 0
    browser = await Browser.launch(headless=not headed, stealth=True, browser=browser_type)
    async with browser:
        tab = await browser.new_tab("about:blank")
        for name, expr, ok in local_tests:
            try:
                result = await tab.eval(expr)
                passed = bool(ok(result))
            except Exception as e:  # noqa: BLE001 - report every failure
                result, passed = f"ERROR {e}", False
            failures += not passed
            print(f"  {name:<36} {'PASS' if passed else 'FAIL'}  ({result})")

        if full:
            print("\nLive detection sites:")
            sites = [
                (
                    "bot.sannysoft.com",
                    "https://bot.sannysoft.com/",
                    "document.querySelectorAll('.failed').length",
                    lambda r: r == 0,
                ),
                (
                    "browserscan.net/bot-detection",
                    "https://www.browserscan.net/bot-detection",
                    "!/robot|bot detected/i.test(document.body.innerText) ? 0 : 1",
                    lambda r: r == 0,
                ),
            ]
            for name, url, expr, ok in sites:
                try:
                    await tab.get(url, timeout=45)
                    await asyncio.sleep(6)
                    result = await tab.eval(expr)
                    passed = bool(ok(result))
                except Exception as e:  # noqa: BLE001
                    result, passed = f"ERROR {e}", False
                failures += not passed
                print(f"  {name:<36} {'PASS' if passed else 'FAIL'}  ({result})")
            print(
                "\nFor CreepJS parity run: pytest examples/fingerprint_tests/"
                "test_stock_runtime_parity.py"
            )

    print(f"\nDone. {failures} failure(s).")
    if failures:
        sys.exit(1)


def _show_info() -> None:
    """Show Tellurium installation info."""
    from tellurium import __version__
    from tellurium.browser.launcher import _find_chrome_candidates

    print(f"Tellurium {__version__}\n")

    candidates = _find_chrome_candidates()
    if candidates:
        path, kind = candidates[0]
        print(f"  Browser stock:   {path} ({kind})")
    else:
        print("  Browser stock:   not found")

    browsers = _cache.installed_browsers(_cache_dir())
    if browsers:
        default = next((b for b in browsers if b.is_current), browsers[0])
        print(
            f"  Browser patched: {default.binary} ({default.version}"
            f"{', current' if default.is_current else ''})"
        )
        if len(browsers) > 1:
            print(f"                   +{len(browsers) - 1} more (tellurium list-browsers)")
    else:
        print("  Browser patched: not installed (tellurium download-browser --browser patched)")

    protocol = Path(__file__).parent / "cdp" / "protocol.json"
    print(f"  CDP bindings:    {'bundled' if protocol.exists() else 'not found'}")

    try:
        import maxminddb  # noqa: F401

        from tellurium.stealth.geoip import _ensure_geolite2_db

        try:
            print(f"  GeoIP:           {_ensure_geolite2_db()}")
        except FileNotFoundError:
            print("  GeoIP:           maxminddb installed, no database (tellurium download-geoip)")
    except ImportError:
        print("  GeoIP:           not installed (pip install tellurium[geoip])")

    print(f"  Cache:           {_cache_dir()}")


def _list_browsers() -> None:
    """List installed patched browser versions."""
    browsers = _cache.installed_browsers(_cache_dir())
    if not browsers:
        print("No browsers installed.")
        print("Run 'tellurium download-browser --browser patched' to install one.")
        return

    print("Installed browsers:\n")
    for b in browsers:
        marker = "  (current)" if b.is_current else ""
        print(f"  {b.version}{marker}")
        print(f"    Path: {b.path}")
        sha = b.expected_sha256
        if sha:
            print(f"    SHA256: {sha[:16]}...")
        if b.manifest:
            rel = b.manifest.get("telluride_version") or b.manifest.get("version")
            if rel and rel != b.version:
                print(f"    Release: {rel}")
            if b.manifest.get("security"):
                print(f"    Security release: {', '.join(b.manifest.get('cve', []))}")
        print()


def _update_browser(check_only: bool, security_only: bool) -> None:
    """Check for and optionally install browser updates."""
    from tellurium.browser import _update_check

    cache = _cache_dir()
    installed = _get_installed_version(cache)
    info = _update_check.check_for_update(cache_root=cache, force=True)
    latest = info.latest if info else _check_latest_patched()

    if not latest:
        print("Could not check for updates (network error or no releases found).")
        sys.exit(1)

    if not installed:
        print("No patched browser installed.")
        print(f"Latest available: {latest}")
        if check_only:
            return
        if not _install_patched(latest):
            sys.exit(1)
        return

    if installed == latest:
        print(f"Already up to date: {installed}")
        return

    is_security = bool(info and info.security)
    print(f"Installed: {installed}")
    print(f"Available: {latest}{' (SECURITY release)' if is_security else ''}")

    if check_only:
        print("\nUpdate available. Run 'tellurium update-browser' to install.")
        return
    if security_only and not is_security:
        print("\nNot a security release; skipping (--security-only).")
        return
    if not _install_patched(latest):
        sys.exit(1)


def _prune_browsers(keep: int) -> None:
    """Remove old browser versions, keeping the N most recent (never 'current')."""
    import shutil

    browsers = _cache.installed_browsers(_cache_dir())
    if len(browsers) <= keep:
        print(f"Only {len(browsers)} browser(s) installed, keeping all.")
        return

    to_keep = browsers[:keep]
    to_remove = [b for b in browsers[keep:] if not b.is_current]
    kept_current = [b for b in browsers[keep:] if b.is_current]

    print(f"Keeping {keep} most recent version(s):")
    for b in to_keep + kept_current:
        print(f"  {b.version}{'  (current)' if b.is_current else ''}")

    print(f"\nRemoving {len(to_remove)} old version(s):")
    for b in to_remove:
        print(f"  {b.version}")
        shutil.rmtree(b.path)

    print("\nDone.")


def _verify_browser(reinstall: bool) -> None:
    """Verify browser binary integrity using SHA256 from MANIFEST.json."""
    from tellurium.browser._manifest import _sha256_file

    browsers = _cache.installed_browsers(_cache_dir())
    if not browsers:
        print("No browsers installed.")
        return

    all_valid = True
    for b in browsers:
        expected_hash = b.expected_sha256
        if b.manifest is None:
            print(f"  {b.version}: SKIP (no MANIFEST.json)")
            continue
        if not expected_hash:
            print(f"  {b.version}: SKIP (no SHA256 for this platform in manifest)")
            continue

        try:
            actual_hash = _sha256_file(b.binary)
        except OSError as e:
            print(f"  {b.version}: ERROR ({e})")
            all_valid = False
            continue

        if actual_hash == expected_hash:
            print(f"  {b.version}: OK (SHA256 valid)")
            continue

        print(f"  {b.version}: CORRUPT (SHA256 mismatch)")
        print(f"    Expected: {expected_hash[:16]}...")
        print(f"    Actual:   {actual_hash[:16]}...")
        if reinstall:
            print(f"    Reinstalling {b.version}...")
            if _install_patched(b.version, reinstall=True):
                continue
            print("    Reinstall failed; remove the directory manually and retry:")
            print(f"      {b.path}")
        all_valid = False

    if not all_valid:
        sys.exit(1)

"""Tellurium CLI."""
from __future__ import annotations
import argparse
import asyncio
import sys


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

    args = parser.parse_args()

    if args.command == "update-cdp":
        _update_cdp(args.chrome_version)
    elif args.command == "download-browser":
        asyncio.run(_download_browser(args.browser))
    elif args.command == "stealth-test":
        asyncio.run(_stealth_test(args.browser, args.full))
    elif args.command == "info":
        _show_info()
    else:
        parser.print_help()


def _update_cdp(chrome_version: str | None) -> None:
    """Regenerate CDP bindings from protocol.json."""
    import json
    from pathlib import Path
    from tellurium.cdp.generator import CDPGenerator

    protocol_path = Path(__file__).parent / "cdp" / "protocol.json"
    domains_dir = Path(__file__).parent / "cdp" / "domains"

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

"""``tellurium update-cdp``: regenerate the CDP bindings in ``tellurium/cdp/domains/``
from the bundled ``protocol.json``, or from the one of a given Chrome release."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def register(subparsers: Any) -> None:
    """Add the ``update-cdp`` subcommand; its handler is ``args.run``."""
    parser = subparsers.add_parser("update-cdp", help="Regenerate CDP bindings")
    parser.add_argument("--chrome-version", help="Target Chrome version")
    parser.set_defaults(run=main)


def main(args: argparse.Namespace) -> None:
    update_cdp(args.chrome_version)


def _protocol_path():
    return Path(__file__).parent / "protocol.json"


def _domains_dir():
    return Path(__file__).parent / "domains"


def update_cdp(chrome_version: str | None) -> None:
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

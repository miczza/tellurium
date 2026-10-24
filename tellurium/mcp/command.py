"""``tellurium mcp`` on the command line: its options, and a clear message when
the ``mcp`` extra is missing. Imports no SDK until the command runs."""

from __future__ import annotations

import argparse
import sys
from typing import Any

INSTALL_HINT = "tellurium mcp needs the MCP SDK: pip install 'tellurium[mcp]'"


def register(subparsers: Any) -> None:
    """Add the ``mcp`` subcommand; its handler is ``args.run``."""
    parser = subparsers.add_parser(
        "mcp", help="Run tellurium as an MCP server on stdio (needs tellurium[mcp])"
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser windows")
    parser.add_argument(
        "--allow-eval", action="store_true", help="List the eval tool (always on with stdio)"
    )
    parser.set_defaults(run=main)


def main(args: argparse.Namespace) -> None:
    """Serve MCP on stdio until the client leaves (``eval`` is on: a local client)."""
    try:
        from tellurium.mcp import server
        from tellurium.mcp.config import ServerConfig, default_home
    except ModuleNotFoundError as exc:
        if (exc.name or "").partition(".")[0] != "mcp":
            raise
        print(INSTALL_HINT, file=sys.stderr)
        sys.exit(2)
    config = ServerConfig(home=default_home(), headed=args.headed, allow_eval=True)
    server.run(config, "stdio")

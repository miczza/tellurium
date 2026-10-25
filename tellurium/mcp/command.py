"""``tellurium mcp`` on the command line: its options, and a clear message when
the ``mcp`` extra is missing. Imports no SDK until the command runs."""

from __future__ import annotations

import argparse
import math
import sys
from typing import Any

INSTALL_HINT = "tellurium mcp needs the MCP SDK: pip install 'tellurium[mcp]'"


def register(subparsers: Any) -> None:
    """Add the ``mcp`` subcommand; its handler is ``args.run``."""
    parser = subparsers.add_parser(
        "mcp",
        help="Run tellurium as an MCP server on stdio, or on HTTP with --http (needs tellurium[mcp])",
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser windows")
    parser.add_argument(
        "--allow-local-urls",
        action="store_true",
        help="Let the agent open file:, chrome: and other non-web URLs",
    )
    http = parser.add_argument_group("HTTP (Streamable HTTP, Bearer token required)")
    http.add_argument(
        "--http",
        metavar="HOST:PORT",
        help="Serve on HTTP instead of stdio, e.g. 127.0.0.1:8765 (port 0: any free one)",
    )
    http.add_argument(
        "--allow-eval", action="store_true", help="Offer the eval tool over HTTP (off by default)"
    )
    http.add_argument(
        "--idle-timeout",
        type=float,
        metavar="SECONDS",
        help="Close and save a client's sessions after this long without a call "
        "(default 900; 0: never)",
    )
    http.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow binding --http to a non-loopback address (the network can reach it)",
    )
    http.add_argument(
        "--max-sessions-per-client",
        type=int,
        metavar="N",
        help="Browsers one client may run at once (default 4)",
    )
    http.add_argument(
        "--max-sessions",
        type=int,
        metavar="N",
        help="Browsers the whole server may run at once (default 16)",
    )
    parser.set_defaults(run=main)


def main(args: argparse.Namespace) -> None:
    """Serve MCP on stdio until the client leaves (``eval`` is on: a local client),
    or on HTTP with ``--http`` until stopped (``eval`` only with ``--allow-eval``)."""
    try:
        from tellurium.mcp import server
        from tellurium.mcp.config import ServerConfig, default_home
    except ModuleNotFoundError as exc:
        if (exc.name or "").partition(".")[0] != "mcp":
            raise
        print(INSTALL_HINT, file=sys.stderr)
        sys.exit(2)
    http = _http_config(args) if args.http else None
    http_only = (args.idle_timeout, args.max_sessions_per_client, args.max_sessions)
    if http is None and (args.allow_remote or any(v is not None for v in http_only)):
        _fail("--idle-timeout, --allow-remote and --max-sessions* need --http")
    config = ServerConfig(
        home=default_home(),
        headed=args.headed,
        allow_eval=True if http is None else args.allow_eval,
        allow_local_urls=args.allow_local_urls,
        http=http,
    )
    server.run(config, "stdio" if http is None else "http")


def _http_config(args: argparse.Namespace) -> Any:
    from tellurium.mcp import auth
    from tellurium.mcp.config import DEFAULT_IDLE_TIMEOUT, HttpConfig

    try:
        host, port = auth.parse_bind(args.http)
    except ValueError as exc:
        _fail(str(exc))
    if not auth.is_loopback(host):
        if not args.allow_remote:
            _fail(
                f"{host} is not a loopback address: anyone on the network could reach the "
                "server (the token still applies). Pass --allow-remote to do it anyway."
            )
        print(
            f"tellurium mcp: WARNING: listening on {host}, reachable from the network; "
            "anyone with the token drives your browsers",
            file=sys.stderr,
        )
    idle = DEFAULT_IDLE_TIMEOUT if args.idle_timeout is None else args.idle_timeout
    if not math.isfinite(idle) or idle < 0:
        _fail("--idle-timeout must be 0 (never) or a finite number of seconds")
    caps = {}
    for flag, field in (
        ("--max-sessions-per-client", "max_sessions_per_client"),
        ("--max-sessions", "max_sessions"),
    ):
        value = getattr(args, field)
        if value is not None:
            if value < 1:
                _fail(f"{flag} must be at least 1")
            caps[field] = value
    return HttpConfig(host=host, port=port, idle_timeout=idle or None, **caps)


def _fail(message: str) -> None:
    print(f"tellurium mcp: {message}", file=sys.stderr)
    sys.exit(2)

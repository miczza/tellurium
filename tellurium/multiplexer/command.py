"""``tellurium multiplex`` on the command line: its options, the proxies file,
and a clear message when the ``multiplex`` extra or the patched Chrome is
missing. Imports no ``websockets`` until the command runs.

It prints where it listens and where the token is, never the token itself
nor a proxy's credentials; SIGINT (Ctrl-C) and SIGTERM close every Chrome,
forwarder and profile, then it exits with 0.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import math
import signal
import sys
from pathlib import Path
from typing import Any

INSTALL_HINT = "tellurium multiplex needs websockets: pip install 'tellurium[multiplex]'"
DEFAULT_LISTEN = "127.0.0.1:9339"
_SHAPE = "scheme://[user:password@]host:port, or host:port"


class ProxiesFileError(ValueError):
    """A proxies file that cannot be used; the message never quotes a line."""


def register(subparsers: Any) -> None:
    """Add the ``multiplex`` subcommand; its handler is ``args.run``."""
    parser = subparsers.add_parser(
        "multiplex",
        help="Serve one CDP endpoint (Playwright, Puppeteer) in front of a pool of Chromes, "
        "one Chrome per connection (needs tellurium[multiplex])",
    )
    parser.add_argument(
        "--pool", type=int, required=True, metavar="N", help="Chromes running at most"
    )
    parser.add_argument(
        "--proxies",
        type=Path,
        metavar="FILE",
        help="Proxy URLs, one per line (blank lines and # comments skipped), used in turn",
    )
    parser.add_argument(
        "--warm", type=int, default=0, metavar="K", help="Chromes kept ready with no client"
    )
    parser.add_argument(
        "--listen",
        default=DEFAULT_LISTEN,
        metavar="HOST:PORT",
        help=f"Where to listen (default {DEFAULT_LISTEN}; port 0: any free one)",
    )
    parser.add_argument(
        "--acquire-timeout",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="How long a client waits in the queue for a free Chrome (then HTTP 503)",
    )
    parser.add_argument(
        "--browser",
        default="patched",
        choices=["stock", "patched"],
        help="patched (default): chromium-telluride; stock: the Chrome found on this system",
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser windows")
    parser.set_defaults(run=main)


def read_proxies(path: Path) -> list[str]:
    """The proxy URLs of *path*, one per line; blank lines and ``#`` comments
    are skipped. A bad line raises :class:`ProxiesFileError` with its number,
    never its text (it may hold a password)."""
    from tellurium.browser.proxy import parse_proxy_url

    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ProxiesFileError(
            f"cannot read the proxies file {path}: {type(exc).__name__}"
        ) from None
    proxies = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            if any(c.isspace() for c in line):
                raise ValueError
            info = parse_proxy_url(line)
            if not info["host"]:
                raise ValueError
        except ValueError:
            raise ProxiesFileError(
                f"line {number} of {path} is not a proxy URL (expected {_SHAPE})"
            ) from None
        proxies.append(line)
    if not proxies:
        raise ProxiesFileError(f"no proxy in {path}")
    return proxies


def main(args: argparse.Namespace) -> None:
    """Serve until SIGINT or SIGTERM, then close everything and exit with 0."""
    try:
        from tellurium.multiplexer.server import require_websockets

        require_websockets()
    except ImportError:
        _fail(INSTALL_HINT)
    from tellurium.access import TokenFileError, is_loopback, parse_bind
    from tellurium.multiplexer import Multiplexer

    try:
        host, port = parse_bind(args.listen)
    except ValueError as exc:
        _fail(f"--listen: {exc}")
    if args.pool < 1:
        _fail("--pool must be at least 1")
    if not 0 <= args.warm <= args.pool:
        _fail(f"--warm must be between 0 and --pool ({args.pool})")
    if not (math.isfinite(args.acquire_timeout) and args.acquire_timeout > 0):
        _fail("--acquire-timeout must be a positive number of seconds")
    proxies: list[str] = []
    if args.proxies is not None:
        try:
            proxies = read_proxies(args.proxies)
        except ProxiesFileError as exc:
            _fail(str(exc))
    if args.browser == "patched" and not _patched_installed():
        _fail(
            "no patched Chrome (chromium-telluride) is installed: run "
            "`tellurium download-browser --browser patched`, or pass --browser stock"
        )
    mux = Multiplexer(
        args.pool,
        proxies=proxies,
        warm=args.warm,
        acquire_timeout=args.acquire_timeout,
        headless=not args.headed,
        browser=args.browser,
    )
    if not is_loopback(host):
        _say(
            f"WARNING: listening on {host}, reachable from the network; "
            "anyone with the token drives your browsers"
        )
    try:
        asyncio.run(_serve(mux, host, port, len(proxies)))
    except KeyboardInterrupt:  # before the signal handlers were in place
        _say("stopped")
    except OSError as exc:
        _fail(f"cannot listen on {args.listen}: {exc.strerror or exc}")
    except TokenFileError as exc:
        _fail(str(exc))


async def _serve(mux: Any, host: str, port: int, proxies: int) -> None:
    serving = asyncio.ensure_future(mux.serve(host, port))
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, serving.cancel)
    try:
        while mux.url is None and not serving.done():
            await asyncio.wait([serving], timeout=0.05)
        if mux.url is not None:
            via = f", {proxies} prox{'y' if proxies == 1 else 'ies'} in turn" if proxies else ""
            print(f"tellurium multiplex: {mux.url} ({mux.status()['size']} Chromes{via})")
            print(f"tellurium multiplex: token in {mux.token_file}")
            print(
                "tellurium multiplex: connect_over_cdp(url, "
                'headers={"Authorization": "Bearer <token>"}); Ctrl-C to stop',
                flush=True,
            )
        with contextlib.suppress(asyncio.CancelledError):
            await serving
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)
        if not serving.done():
            serving.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await serving
    _say("stopped")


def _patched_installed() -> bool:
    from tellurium.browser import _cache

    return bool(_cache.installed_browsers())


def _say(message: str) -> None:
    print(f"tellurium multiplex: {message}", file=sys.stderr, flush=True)


def _fail(message: str) -> None:
    _say(message)
    sys.exit(2)

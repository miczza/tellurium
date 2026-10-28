"""``tellurium login NAME [URL] [--dir D]``: sign in to a named session by hand.

Chrome opens with a window on the session (``~/.tellurium/sessions/NAME`` by
default, the folder ``tellurium mcp`` uses, with the same stealth launch; without
stealth for a session saved with its own ``--user-agent``), on
*URL* if given. The person signs in (2FA and captchas included), then clicks
"Done" on the banner, presses Enter in the terminal, or closes the window. The
session is then saved: ``session.json`` and the cookie jar in ``cookies.json``,
which Chrome is still alive to hand over even after its last window is gone
(the cookies it drops with its last window are put back first).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
from typing import IO, Any

from tellurium.browser.navigation import NavigationError
from tellurium.cdp.types import CDPError
from tellurium.session import session_cookies, stealth_choice
from tellurium.session.errors import SessionBusyError
from tellurium.session.session import Session

#: Keeps Chrome running after its last window closes, so the cookie jar can
#: still be read (Chrome drops the cookies with no expiry when it exits).
KEEP_ALIVE = "--keep-alive-for-test"
REASON = "Sign in, then click Done, press Enter in the terminal or close the window."
#: Seconds between two looks at whether any window is left.
POLL = 0.3
#: Bound on each CDP call made while waiting.
CALL_TIMEOUT = 5.0
NAVIGATION_TIMEOUT = 30.0


def register(subparsers: Any) -> None:
    """Add the ``login`` subcommand; its handler is ``args.run``."""
    parser = subparsers.add_parser(
        "login", help="Open a session in a browser window and sign in by hand"
    )
    parser.add_argument("name", help="Session name")
    parser.add_argument("url", nargs="?", help="Page to open (e.g. the site's login page)")
    parser.add_argument(
        "--dir", help="Folder of the sessions (default: ~/.tellurium/sessions, as tellurium mcp)"
    )
    parser.set_defaults(run=main)


def main(args: argparse.Namespace) -> None:
    directory = args.dir or str(_default_dir())
    try:
        path = asyncio.run(
            login(args.name, args.url, directory=directory, enter=sys.stdin.isatty())
        )
    except SessionBusyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    print(f"Session {args.name!r} saved in {path}")


def _default_dir():
    from tellurium.mcp.config import default_home  # no MCP SDK behind it

    return default_home() / "sessions"


async def login(name: str, url: str | None = None, *, directory: str, enter: bool = False) -> str:
    """Open session *name* under *directory* headed, on *url*, until the person
    is done (*enter*: Enter in the terminal counts too); save it and return its
    folder. ``SessionBusyError`` if another process has it open."""
    session = await asyncio.to_thread(Session, name, path=os.path.join(directory, name))
    hints = session._launch_hints
    args = [*(hints.get("args") or []), KEEP_ALIVE]
    stealth = stealth_choice.stealth_for(session)
    async with session.start(headless=False, stealth=stealth, args=args) as browser:
        await asyncio.to_thread(session.save)  # the seed survives a crash
        tab = browser.main_tab
        if url:
            try:
                await tab.get(url, wait_until="commit", timeout=NAVIGATION_TIMEOUT)
            except (TimeoutError, NavigationError) as exc:
                print(f"Warning: could not open {url}: {exc}", file=sys.stderr)
        await _until_done(browser, tab, sys.stdin if enter else None)
    await asyncio.to_thread(session.save)
    return session.path


async def _until_done(browser: Any, tab: Any, stdin: IO[str] | None) -> None:
    """Until "Done", Enter on *stdin* (if given) or no window is left."""
    waiters = [_done_clicked(tab), _windows_closed(browser)]
    if stdin is not None:
        waiters.append(enter_pressed(stdin))
    tasks = [asyncio.ensure_future(w) for w in waiters]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()  # a watcher that failed fails the login
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _done_clicked(tab: Any) -> None:
    try:
        await tab.wait_for_human(REASON, timeout=None)
    except (ConnectionError, CDPError):
        await asyncio.Event().wait()  # its tab is gone: the windows decide


async def _windows_closed(browser: Any) -> None:
    """Until no window is left. Chrome ends its browsing session with its last
    window, dropping the cookies with no expiry: the jar is read as long as a
    window is open, and what Chrome dropped is put back once they are all gone
    (so the session's close finds it). A cookie set in the last :data:`POLL`
    seconds before the window closed can be missed."""
    root = browser._router.root
    jar: list = []
    try:
        while True:
            try:
                candidate = await session_cookies.snapshot(browser)
            except asyncio.TimeoutError:
                candidate = None
            if not await _windows_open(root):
                break
            if candidate is not None:
                jar = candidate  # read with a window still open: the whole jar
            await asyncio.sleep(POLL)
        reinjection = session_cookies.Reinjection(jar)
        try:
            await reinjection.run(browser)
        finally:
            reinjection.drop()
    except ConnectionError:
        return  # Chrome is gone: the session keeps what it had


async def _windows_open(root: Any) -> bool:
    targets = await root.send("Target.getTargets", {}, timeout=CALL_TIMEOUT)
    return any(t.get("type") == "page" for t in targets.get("targetInfos", []))


async def enter_pressed(stdin: IO[str]) -> None:
    """Until a line (or the end) arrives on *stdin*; no thread left behind on POSIX."""
    loop = asyncio.get_running_loop()
    pressed = loop.create_future()

    def ready() -> None:
        if not pressed.done():
            pressed.set_result(None)

    fd = stdin.fileno()
    try:
        loop.add_reader(fd, ready)
    except (NotImplementedError, OSError, ValueError):  # Windows: no readers on a console
        _read_in_thread(loop, stdin, ready)
        await pressed
        return
    try:
        await pressed
        os.read(fd, 4096)  # consume the line
    finally:
        loop.remove_reader(fd)


def _read_in_thread(loop: asyncio.AbstractEventLoop, stdin: IO[str], ready: Any) -> None:
    def read() -> None:
        stdin.readline()
        try:
            loop.call_soon_threadsafe(ready)
        except RuntimeError:  # the loop is closed: nobody waits any more
            pass

    # A daemon: blocked on the console, it must not keep the process alive.
    threading.Thread(target=read, name="tellurium-login-enter", daemon=True).start()

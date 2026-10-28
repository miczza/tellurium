"""``tellurium login NAME [URL] [--dir D]``: sign in to a named session by hand.

Chrome opens with a window on the session (``~/.tellurium/sessions/NAME`` by
default, the folder ``tellurium mcp`` uses, with the same stealth launch; without
stealth for a session saved with its own ``--user-agent``), on
*URL* if given. The person signs in (2FA and captchas included), then clicks
"Done" on the banner, presses Enter in the terminal, or closes the window. The
session is then saved: ``session.json`` and the cookie jar in ``cookies.json``.

Chrome drops the cookies with no expiry (a sign-in's) when its last window
closes, so a second window of its own, minimized, keeps its browsing session
open while the person works in the first: closing that one ends the login with
the whole jar, a cookie written an instant before included. If the person
closes both, Chrome stays up anyway (:data:`KEEP_ALIVE`) and the jar read
while a window was open is put back (a cookie of its last :data:`POLL`
seconds can then be missed).
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
#: still be read (Chrome drops the cookies with no expiry when it exits):
#: the fallback for when the keeper window is closed too.
KEEP_ALIVE = "--keep-alive-for-test"
REASON = "Sign in, then click Done, press Enter in the terminal or close the window."
#: Seconds between two looks at whether any window is left.
POLL = 0.3
#: Bound on each CDP call made while waiting.
CALL_TIMEOUT = 5.0
NAVIGATION_TIMEOUT = 30.0
#: The page of the window that keeps Chrome's browsing session open.
KEEPER_URL = (
    "data:text/html,<title>tellurium login: keep this window</title>"
    "<p>This window keeps the sign-in session open. Sign in in the other window, then close it."
)


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
        await session.save_now()  # the seed survives a crash
        tab = browser.main_tab
        keeper = await _open_keeper(browser)
        if url:
            try:
                await tab.get(url, wait_until="commit", timeout=NAVIGATION_TIMEOUT)
            except (TimeoutError, NavigationError) as exc:
                print(f"Warning: could not open {url}: {exc}", file=sys.stderr)
        await _until_done(browser, tab, sys.stdin if enter else None, keeper)
    await session.save_now()
    return session.path


async def _until_done(
    browser: Any, tab: Any, stdin: IO[str] | None, keeper: str | None = None
) -> None:
    """Until "Done", Enter on *stdin* (if given) or no window but the
    *keeper* is left."""
    waiters = [_done_clicked(tab), _windows_closed(browser, keeper)]
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


async def _open_keeper(browser: Any) -> str | None:
    """A minimized window of Chrome's own (its target id), so the person
    closing theirs does not end the browsing session; ``None`` if it cannot
    be opened (the login then relies on :data:`KEEP_ALIVE`)."""
    root = browser._router.root
    try:
        created = await root.send(
            "Target.createTarget",
            {"url": KEEPER_URL, "newWindow": True, "background": True},
            timeout=CALL_TIMEOUT,
        )
    except (asyncio.TimeoutError, CDPError, ConnectionError):
        return None
    keeper = created["targetId"]
    try:
        window = await root.send(
            "Browser.getWindowForTarget", {"targetId": keeper}, timeout=CALL_TIMEOUT
        )
        await root.send(
            "Browser.setWindowBounds",
            {"windowId": window["windowId"], "bounds": {"windowState": "minimized"}},
            timeout=CALL_TIMEOUT,
        )
    except (asyncio.TimeoutError, CDPError, ConnectionError):
        pass  # shown, not minimized: it still keeps the session
    return keeper


async def _done_clicked(tab: Any) -> None:
    try:
        await tab.wait_for_human(REASON, timeout=None)
    except (ConnectionError, CDPError):
        await asyncio.Event().wait()  # its tab is gone: the windows decide


async def _windows_closed(browser: Any, keeper: str | None) -> None:
    """Until no window but the *keeper* is left. With the keeper still open
    Chrome's jar is whole and the session's close reads it. If the keeper is
    gone too, Chrome has ended its browsing session with its last window,
    dropping the cookies with no expiry: the jar read while a window was open
    is put back (so the session's close finds it); a cookie set in the last
    :data:`POLL` seconds before can then be missed."""
    root = browser._router.root
    jar: list = []
    try:
        while True:
            try:
                candidate = await session_cookies.snapshot(browser)
            except asyncio.TimeoutError:
                candidate = None
            pages = await _pages(root)
            if not pages - {keeper}:
                if keeper in pages:
                    return
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


async def _pages(root: Any) -> set[str]:
    targets = await root.send("Target.getTargets", {}, timeout=CALL_TIMEOUT)
    return {t["targetId"] for t in targets.get("targetInfos", []) if t.get("type") == "page"}


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

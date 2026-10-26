"""A separate process holding a named session, for the tests that need two.

``python session_child.py write PATH URL`` opens the session, loads the pages
that set cookies with no expiry, writes one more cookie right before closing,
saves and exits. ``python session_child.py read PATH`` opens it again and
prints the names of its cookies as JSON. ``python session_child.py hold PATH``
opens it, prints ``ready`` and waits until it is killed.
"""

from __future__ import annotations

import asyncio
import json
import sys

from tellurium import Session


async def write(path: str, base: str) -> None:
    session = Session("child", path=path)
    async with session.start(headless=True) as browser:
        tab = await browser.get(f"{base}/session-cookie")
        await tab.get(f"{base}/session_cookie.html")
        await tab.eval("document.cookie = 'late=1; path=/; max-age=3600'")
        session.save()


async def read(path: str) -> None:
    session = Session("child", path=path)
    async with session.start(headless=True) as browser:
        names = sorted(c.name for c in await browser.get_cookies("127.0.0.1"))
    print(json.dumps(names), flush=True)


async def hold(path: str) -> None:
    session = Session("child", path=path)
    async with session.start(headless=True):
        print("ready", flush=True)
        await asyncio.Event().wait()


def main() -> None:
    mode, path, *rest = sys.argv[1:]
    runs = {"write": lambda: write(path, rest[0]), "read": lambda: read(path)}
    runs["hold"] = lambda: hold(path)
    asyncio.run(runs[mode]())


if __name__ == "__main__":
    main()

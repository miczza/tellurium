"""The session's cookie jar, kept in ``cookies.json`` next to the profile.

Chrome's profile is not enough to carry a login across a restart: cookies with
no expiry (``expires == -1``: SSO, banks) are dropped when Chrome restarts, and
a cookie written an instant before the close can be lost too (Chrome can stop
before its cookie store commits it). So :func:`snapshot` reads the jar before
Chrome closes, :func:`save` keeps the cookies not yet expired, and after the
next launch :func:`restore` puts back those Chrome does not have, leaving the
ones it kept untouched (its copy is the faithful one).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import warnings
from typing import Any

from tellurium.browser.cookie import Cookie
from tellurium.session import storage

COOKIES_FILE = "cookies.json"
#: Bound on each cookie call to Chrome: a crashed or hung Chrome must not stall
#: a start or a close.
TIMEOUT = 5.0


def _file(folder: str) -> str:
    return os.path.join(folder, COOKIES_FILE)


def _live(cookies: list[Cookie]) -> list[Cookie]:
    """Those with no expiry, or one still ahead."""
    now = time.time()
    return [c for c in cookies if c.expires == -1 or c.expires > now]


def _key(cookie: Cookie) -> tuple[str, str, str, str | None]:
    """What tells two cookies of a jar apart: the same name, domain and path
    in another CHIPS partition is another cookie."""
    partition = cookie.partition_key
    return (
        cookie.name,
        cookie.domain,
        cookie.path,
        None if partition is None else json.dumps(partition, sort_keys=True),
    )


def save(folder: str, cookies: list[Cookie]) -> None:
    """Write the cookies of *cookies* not yet expired to ``cookies.json`` (0600)."""
    payload = {"cookies": [c.to_json() for c in _live(cookies)]}
    storage.write_private(_file(folder), payload)


def load(folder: str) -> list[Cookie]:
    """The cookies of ``cookies.json`` not yet expired; none if it is missing,
    a warning and none if it cannot be read (a bad file never blocks a start)."""
    try:
        with open(_file(folder), encoding="utf-8") as f:
            raw: Any = json.load(f)
        return _live([Cookie.from_json(c) for c in raw["cookies"]])
    except FileNotFoundError:
        return []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        warnings.warn(f"ignoring unreadable {_file(folder)}: {exc}", stacklevel=2)
        return []


async def snapshot(browser: Any) -> list[Cookie]:
    """The browser's cookies, read within :data:`TIMEOUT`."""
    return await asyncio.wait_for(browser.get_cookies(), TIMEOUT)


async def restore(browser: Any, saved: list[Cookie]) -> None:
    """Put back the cookies of *saved* the browser lacks (same name, domain,
    path and partition), each call within :data:`TIMEOUT`."""
    if not saved:
        return
    present = {_key(c) for c in await snapshot(browser)}
    missing = [c for c in saved if _key(c) not in present]
    if missing:
        await asyncio.wait_for(browser.set_cookies(missing), TIMEOUT)

"""The session's cookies with no expiry, kept in ``cookies.json``.

Chrome keeps only cookies with an expiry in its profile: those with none
(``expires == -1``: SSO, banks) are gone when it restarts, so the session
keeps them itself. :func:`snapshot` reads them from Chrome before it closes;
the round trip to Chrome's cookie store also lets a cookie the page wrote an
instant earlier land in the profile, which a bare close can lose.
:func:`restore` puts them back after the next launch.
"""

from __future__ import annotations

import asyncio
import json
import os
import warnings
from typing import Any

from tellurium.browser.cookie import Cookie
from tellurium.session import storage

COOKIES_FILE = "cookies.json"
#: Bound on each cookie call to Chrome: a crashed or hung Chrome must not stall
#: the close.
TIMEOUT = 5.0


def _file(folder: str) -> str:
    return os.path.join(folder, COOKIES_FILE)


def _no_expiry(cookies: list[Cookie]) -> list[Cookie]:
    return [c for c in cookies if c.expires == -1]


def save(folder: str, cookies: list[Cookie]) -> None:
    """Write the cookies of *cookies* with no expiry to ``cookies.json`` (0600)."""
    payload = {"cookies": [c.to_json() for c in _no_expiry(cookies)]}
    storage.write_private(_file(folder), payload)


def load(folder: str) -> list[Cookie]:
    """The cookies of ``cookies.json``; none if it is missing, a warning and
    none if it cannot be read (a bad file never blocks a start)."""
    try:
        with open(_file(folder), encoding="utf-8") as f:
            raw: Any = json.load(f)
        return _no_expiry([Cookie.from_json(c) for c in raw["cookies"]])
    except FileNotFoundError:
        return []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        warnings.warn(f"ignoring unreadable {_file(folder)}: {exc}", stacklevel=2)
        return []


async def snapshot(browser: Any) -> list[Cookie]:
    """The browser's cookies with no expiry, read within :data:`TIMEOUT`."""
    return _no_expiry(await asyncio.wait_for(browser.get_cookies(), TIMEOUT))


async def restore(browser: Any, cookies: list[Cookie]) -> None:
    """Put *cookies* back in the browser, within :data:`TIMEOUT`."""
    if cookies:
        await asyncio.wait_for(browser.set_cookies(cookies), TIMEOUT)

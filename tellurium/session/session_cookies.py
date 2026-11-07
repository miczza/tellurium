"""The session's cookie jar, kept in ``cookies.json`` next to the profile.

Chrome's profile is not enough to carry a login across a restart: cookies with
no expiry (``expires == -1``: SSO, banks) are dropped when Chrome restarts, and
a cookie written an instant before the close can be lost too (Chrome can stop
before its cookie store commits it). So :func:`snapshot` reads the jar before
Chrome closes, :func:`save` keeps the cookies not yet expired, and after the
next launch a :class:`Reinjection` puts back those Chrome does not have, and
those it has with an older value when the file was written as Chrome closed.
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


def save(folder: str, cookies: list[Cookie], *, at_close: bool = False) -> None:
    """Write the cookies of *cookies* not yet expired to ``cookies.json`` (0600);
    *at_close*: they are the jar Chrome had as it closed, newer than its own copy."""
    payload = {"cookies": [c.to_json() for c in _live(cookies)], "at_close": at_close}
    storage.write_private(_file(folder), payload)


def add_missing(folder: str, cookies: list[Cookie]) -> None:
    """Add to ``cookies.json`` those of *cookies* it lacks (same name, domain,
    path and partition); those it has stay as they are, and so does its
    *at_close*."""
    saved, at_close = read(folder)
    have = {_key(c) for c in saved}
    save(folder, saved + [c for c in cookies if _key(c) not in have], at_close=at_close)


def read(folder: str) -> tuple[list[Cookie], bool]:
    """The cookies of ``cookies.json`` not yet expired, and whether they were
    saved as Chrome closed; none if it is missing. A file that cannot be read
    gives a warning and none; one that cannot be parsed (any error, a
    ``RecursionError`` on deep nesting too) is moved to
    ``cookies.json.bad-<time>``, so a bad file never blocks a start and the
    next close writes a good one."""
    path = _file(folder)
    try:
        data = storage.read_bytes(path)
    except FileNotFoundError:
        return [], False
    except OSError as exc:
        warnings.warn(f"ignoring unreadable {path}: {exc}", stacklevel=2)
        return [], False
    try:
        raw: Any = json.loads(data.decode("utf-8"))
        cookies = _live([Cookie.from_json(c) for c in raw["cookies"]])
        return cookies, raw.get("at_close") is True
    except Exception as exc:  # noqa: BLE001 - whatever the content, it is a bad file
        aside = f"{path}.bad-{time.time_ns()}"
        try:
            os.replace(path, aside)
        except OSError:
            aside = None
        where = f", moved to {aside}" if aside else ""
        warnings.warn(f"ignoring unreadable {path}{where}: {exc!r}", stacklevel=2)
        return [], False


def load(folder: str) -> list[Cookie]:
    """The cookies of :func:`read`."""
    return read(folder)[0]


async def snapshot(browser: Any) -> list[Cookie]:
    """The browser's cookies, read within :data:`TIMEOUT`."""
    return await asyncio.wait_for(browser.get_cookies(), TIMEOUT)


class Reinjection:
    """The cookies of ``cookies.json`` a start puts back into Chrome, and what
    the close must keep of them if Chrome never confirmed they went in.

    :meth:`run` sends Chrome those it lacks (same name, domain, path and
    partition), each call within :data:`TIMEOUT`; with *saved_wins* (the file
    was written as Chrome closed, so it is newer than Chrome's own copy, which
    may miss the last changes: a rotated token) also those Chrome has with
    another value. Without it (the last run never closed: Chrome's copy may be
    the newer) Chrome's are left alone. Until Chrome has taken them
    (a timeout, a cancelled start, a Chrome gone) they stay *pending*, and
    :meth:`keep` adds them to the jar the close reads, so a failed restore
    never costs the saved cookies. A call that timed out is not given up: its
    late answer still counts (the jar Chrome had, or that it took the cookies),
    until :meth:`drop`. So a cookie Chrome has set anew meanwhile (the site
    logged in again) is Chrome's, not ours, and one Chrome had or took and the
    site deleted stays deleted.
    """

    def __init__(self, saved: list[Cookie], *, saved_wins: bool = False) -> None:
        self.pending = list(saved)
        self._saved_wins = saved_wins
        # Chrome's jar as the start found it; None until read.
        self._seen: dict[tuple, Cookie] | None = None
        self._calls: set[asyncio.Future] = set()  # those still to answer

    async def run(self, browser: Any) -> None:
        if not self.pending:
            return
        jar = await self._answer(browser.get_cookies(), self._saw)
        self._saw(jar)
        if self.pending:
            await self._answer(browser.set_cookies(self.pending), self._took)
        self._took(None)  # in Chrome now: from here on its jar is the truth

    def keep(self, jar: list[Cookie]) -> list[Cookie]:
        """*jar* (Chrome's at the close) with the pending cookies it lacks, or
        has still as the start found them (and must take ours over)."""
        kept = {_key(c): c for c in jar}
        for cookie in self.pending:
            key = _key(cookie)
            current = kept.get(key)
            if self._seen is None:  # Chrome's jar never seen: put back what it lacks
                restore = current is None
            else:
                before = self._seen.get(key)
                restore = self._differs(cookie, before) and current == before
            if restore:
                kept[key] = cookie
        return list(kept.values())

    def drop(self) -> None:
        """Stop waiting for the late answers (the close has read the jar)."""
        for call in self._calls:
            call.cancel()
        self._calls.clear()

    async def _answer(self, call: Any, late: Any) -> Any:
        """The answer of *call* within :data:`TIMEOUT`; past it (or if the
        start is cancelled) *late* gets the answer when it comes."""
        future = asyncio.ensure_future(call)
        try:
            return await asyncio.wait_for(asyncio.shield(future), TIMEOUT)
        except BaseException:
            if future.done():  # it failed, or answered just as the wait ended
                self._landed(future, late)
                raise
            self._calls.add(future)
            future.add_done_callback(lambda f: self._landed(f, late))
            raise

    def _landed(self, future: asyncio.Future, late: Any) -> None:
        self._calls.discard(future)
        if not future.cancelled() and future.exception() is None:
            late(future.result())

    def _saw(self, jar: list[Cookie]) -> None:
        if self._seen is not None:
            return
        self._seen = {_key(c): c for c in jar}
        seen = self._seen
        self.pending = [c for c in self.pending if self._differs(c, seen.get(_key(c)))]

    def _took(self, _: Any) -> None:
        self.pending = []

    def _differs(self, cookie: Cookie, chrome: Cookie | None) -> bool:
        """Whether *cookie* must go back over Chrome's copy *chrome*."""
        return chrome is None or (self._saved_wins and chrome != cookie)

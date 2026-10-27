"""robots.txt: parsed as RFC 9309 says, downloaded through Chrome, cached per browser.

The file is fetched with ``Network.loadNetworkResource``, never from Python,
so it leaves through Chrome's network stack (proxy, IP, TLS) of the tab's browser
context. The load runs in a hidden ``about:blank`` target of that context: from
the tab itself it would be subject to the page's Content-Security-Policy. One
download per origin at a time, kept 24 hours.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
import urllib.parse
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tellurium.browser.navigation import NavigationError, NavigationTimeoutError
from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.tab import Tab

logger = logging.getLogger("tellurium")

MAX_BYTES = 500 * 1024  # RFC 9309 §2.5: parse at least the first 500 KiB
FETCH_TIMEOUT = 10.0  # the whole download: request, redirects, body
CACHE_TTL = 24 * 3600.0  # RFC 9309 §2.4
ERROR_TTL = 60.0  # an unreachable robots.txt is asked again after a minute
CACHE_SIZE = 256  # origins kept per browser, least recently used out first
_READ_CHUNK = 64 * 1024
_CLOSE_TIMEOUT = 2.0
_OPEN_TIMEOUT = 5.0  # creating and attaching the hidden target

_AGENT = re.compile(r"[A-Za-z_-]+")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
_DEFAULT_PORTS = {"http": 80, "https": 443}


class RobotsDisallowedError(NavigationError):
    """``robots.txt`` of *origin* disallows *path*: the navigation was not started."""

    def __init__(self, url: str, origin: str, path: str):
        self.url = url
        self.origin = origin
        self.path = path
        self.error_text = f"robots.txt of {origin} disallows {path}"
        RuntimeError.__init__(self, self.error_text)


@dataclass(frozen=True)
class RobotsRules:
    """The rules of one group: ``(pattern, allow)`` pairs, patterns normalised."""

    rules: tuple[tuple[str, bool], ...]

    def allows(self, target: str) -> bool:
        """Whether *target* (path and query) may be crawled: the longest matching
        pattern decides, ``allow`` on a tie; ``/robots.txt`` always may."""
        path = _normalise(target or "/")
        if path == "/robots.txt":
            return True
        best, allowed = -1, True
        for pattern, allow in self.rules:
            if (len(pattern) > best or (len(pattern) == best and allow)) and _matches(
                pattern, path
            ):
                best, allowed = len(pattern), allow
        return allowed


ALLOW_ALL = RobotsRules(())
DISALLOW_ALL = RobotsRules((("/", False),))


def parse(text: str, agent: str = "*") -> RobotsRules:
    """The rules of *text* (its first 500 KiB) for the product token *agent*: the
    groups naming it, merged, else the ``*`` groups, else none (everything allowed)."""
    wanted = agent.lower()
    if len(text) > MAX_BYTES // 4:  # maybe over the limit once encoded
        raw = text.encode("utf-8", errors="replace")
        if len(raw) > MAX_BYTES:  # the last line may be cut: dropped
            text = raw[:MAX_BYTES].decode("utf-8", errors="ignore").rpartition("\n")[0]
    groups: dict[str, list[tuple[str, bool]]] = {}
    current: list[list[tuple[str, bool]]] = []
    in_rules = False
    for line in text.lstrip("\ufeff").splitlines():
        key, sep, value = line.split("#", 1)[0].partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if in_rules:
                current, in_rules = [], False
            token = "*" if value.startswith("*") else _product_token(value)
            if token:
                current.append(groups.setdefault(token, []))
        elif key in ("allow", "disallow"):
            in_rules = True
            if value:  # an empty disallow forbids nothing
                for rules in current:
                    rules.append((_normalise(value), key == "allow"))
    chosen = groups.get(wanted) if wanted != "*" else None
    if chosen is None:
        chosen = groups.get("*", [])
    return RobotsRules(tuple(chosen))


def outcome(status: int | None, body: bytes, agent: str) -> RobotsRules:
    """RFC 9309 §2.3.1: 2xx → its rules; 4xx → everything allowed; anything else
    (5xx, no answer) → everything disallowed."""
    if status is not None and 200 <= status < 300:
        return parse(body[: MAX_BYTES + 1].decode("utf-8", errors="replace"), agent)
    if status is not None and 400 <= status < 500:
        return ALLOW_ALL
    return DISALLOW_ALL


def split_url(url: str) -> tuple[str, str] | None:
    """``(origin, path?query)`` of an ``http(s)`` *url*; ``None`` for any other."""
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS or not parts.hostname:
        return None
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        host += f":{port}"
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return f"{scheme}://{host}", path


def _product_token(value: str) -> str:
    match = _AGENT.match(value)
    return match.group(0).lower() if match else ""


def _normalise(path: str) -> str:
    """RFC 9309 §2.2.2: octets outside US-ASCII percent-encoded, escapes of
    unreserved characters decoded, the others kept (hex in upper case)."""

    def unescape(m: re.Match) -> str:
        char = chr(int(m.group(1), 16))
        return char if char in _UNRESERVED else f"%{m.group(1).upper()}"

    encoded = "".join(c if ord(c) < 128 else "".join(f"%{b:02X}" for b in c.encode()) for c in path)
    return _ESCAPE.sub(unescape, encoded)


def _matches(pattern: str, path: str) -> bool:
    """Whether *pattern* (``*`` any run, ``$`` at the end the end) matches the
    start of *path*. Kept to positions, linear in each: no regex backtracking."""
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    positions = [0]
    for char in pattern:
        if char == "*":
            positions = list(range(positions[0], len(path) + 1))
        else:
            positions = [p + 1 for p in positions if p < len(path) and path[p] == char]
        if not positions:
            return False
    return len(path) in positions if anchored else True


def _now() -> float:
    return time.monotonic()


@dataclass(frozen=True)
class Frame:
    """The hidden ``about:blank`` target robots.txt is loaded from."""

    session: Any
    target_id: str


async def open_frame(browser: Any, context_id: str) -> Frame:
    """A hidden blank target in *context_id* (``""``: the default context),
    attached. Hidden targets are of type ``other``: no Tab is made for them."""
    root = browser._router.root
    params: dict[str, Any] = {"url": "about:blank", "hidden": True}
    if context_id:
        params["browserContextId"] = context_id
    target_id = (await root.send("Target.createTarget", params, timeout=_OPEN_TIMEOUT))["targetId"]
    try:
        session = await browser._router.attach(target_id, timeout=_OPEN_TIMEOUT)
    except BaseException:
        close = root.send("Target.closeTarget", {"targetId": target_id}, timeout=_CLOSE_TIMEOUT)
        task = asyncio.ensure_future(close)  # even when cancelled: never leave it open
        task.add_done_callback(lambda t: t.cancelled() or t.exception())
        raise
    return Frame(session, target_id)


async def download(frame: Frame, origin: str, agent: str) -> tuple[RobotsRules, float]:
    """The rules of *origin*'s robots.txt, loaded from *frame*, and how long to
    keep them. ``ConnectionError`` if the frame's target is gone."""
    url = origin + "/robots.txt"
    try:
        status, body = await asyncio.wait_for(_load(frame, url), FETCH_TIMEOUT)
    except (CDPError, asyncio.TimeoutError, TimeoutError) as exc:
        logger.info("robots.txt of %s unreachable (%s): nothing allowed", origin, exc)
        return DISALLOW_ALL, ERROR_TTL
    if status is None:
        return DISALLOW_ALL, ERROR_TTL
    rules = outcome(status, body, agent)
    return rules, (CACHE_TTL if status < 500 else ERROR_TTL)


async def _load(frame: Frame, url: str) -> tuple[int | None, bytes]:
    """``(status, body)`` of *url*, no cookies sent; status ``None`` when the
    load failed before any response; a redirect loop counts as a 404."""
    session = frame.session
    params = {
        "frameId": frame.target_id,
        "url": url,
        "options": {"disableCache": False, "includeCredentials": False},
    }
    res = await session.send("Network.loadNetworkResource", params, timeout=FETCH_TIMEOUT)
    resource = res.get("resource", {})
    stream = resource.get("stream")
    try:
        status = resource.get("httpStatusCode") or None
        if status is None:
            if resource.get("netErrorName") == "net::ERR_TOO_MANY_REDIRECTS":
                return 404, b""  # RFC 9309 §2.3.1.2: may be taken as unavailable
            logger.info("robots.txt load %s failed: %s", url, resource.get("netErrorName"))
            return None, b""
        return int(status), (await _read(session, stream) if stream else b"")
    finally:
        if stream:
            await _close_stream(session, stream)


async def _read(session: Any, stream: str) -> bytes:
    body = b""
    while len(body) <= MAX_BYTES:
        params = {"handle": stream, "size": _READ_CHUNK}
        chunk = await session.send("IO.read", params, timeout=FETCH_TIMEOUT)
        data = chunk.get("data", "")
        body += base64.b64decode(data) if chunk.get("base64Encoded") else data.encode()
        if chunk.get("eof"):
            break
    return body


async def _close_stream(session: Any, stream: str) -> None:
    try:
        await session.send("IO.close", {"handle": stream}, timeout=_CLOSE_TIMEOUT)
    except (CDPError, ConnectionError, TimeoutError, asyncio.TimeoutError) as exc:
        logger.debug("IO.close of a robots.txt stream failed: %s", exc)


class Robots:
    """A browser's robots.txt policy and cache: *respect* blocks the navigations
    tellurium starts; *agent* picks the group of the file. Entries are per
    browser context and origin (a context may have its own proxy)."""

    def __init__(self, respect: bool = False, agent: str = "*"):
        if agent != "*" and (not isinstance(agent, str) or not _AGENT.fullmatch(agent)):
            raise ValueError(
                f"robots_agent must be '*' or a product token (letters, '-', '_'), got {agent!r}"
            )
        self.respect = bool(respect)
        self.agent = agent
        self._cache: OrderedDict[tuple[str, str], tuple[float, RobotsRules]] = OrderedDict()
        self._flights: dict[tuple[str, str], asyncio.Future] = {}
        self._frames: dict[str, Frame] = {}  # context id -> its hidden target
        self._frame_lock = asyncio.Lock()
        self._closed = False

    async def check(self, tab: Tab, url: str, timeout: float | None = None) -> None:
        """With *respect*, ``RobotsDisallowedError`` if robots.txt forbids *url*."""
        if not self.respect or (split := split_url(url)) is None:
            return
        origin, path = split
        if not (await self.rules(tab, origin, timeout)).allows(path):
            raise RobotsDisallowedError(url, origin, path)

    async def allowed(self, tab: Tab, url: str) -> bool:
        """Whether robots.txt lets *url* be crawled, with or without *respect*."""
        if (split := split_url(url)) is None:
            return True
        origin, path = split
        return (await self.rules(tab, origin)).allows(path)

    async def rules(self, tab: Tab, origin: str, timeout: float | None = None) -> RobotsRules:
        """*origin*'s rules for *tab*'s context: from the cache, from the download
        in flight, or from a new one. The download belongs to this object: a
        caller that gives up (cancelled, *timeout*) leaves it to the others."""
        browser = tab._browser
        context = next((cid for cid, c in browser._contexts.items() if tab in c._tabs), "")
        key = (context, origin)
        if (cached := self._cached(key)) is not None:
            return cached
        flight = self._flights.get(key) or self._start(browser, key)
        done, _ = await asyncio.wait([flight], timeout=timeout)
        if not done:
            raise NavigationTimeoutError(origin + "/robots.txt", "robots.txt", timeout or 0)
        if flight.cancelled():
            raise ConnectionError("The browser closed")
        return flight.result()[0]

    def forget_context(self, context_id: str) -> None:
        """*context_id* was disposed of, its hidden target with it."""
        self._frames.pop(context_id, None)

    def close(self) -> None:
        """Cancel the downloads in flight; their waiters get ``ConnectionError``.
        The hidden targets go with the browser."""
        self._closed = True
        for flight in list(self._flights.values()):
            flight.cancel()

    def _cached(self, key: tuple[str, str]) -> RobotsRules | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry[0] <= _now():
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return entry[1]

    def _start(self, browser: Any, key: tuple[str, str]) -> asyncio.Future:
        if self._closed:
            raise ConnectionError("The browser closed")
        flight = asyncio.ensure_future(self._fetch(browser, *key))
        self._flights[key] = flight
        flight.add_done_callback(lambda _: self._landed(key, flight))
        return flight

    async def _fetch(self, browser: Any, context: str, origin: str) -> tuple[RobotsRules, float]:
        """:func:`download` from the context's hidden target, opened again once
        if it went (closed by someone, crashed)."""
        for attempt in (1, 2):
            frame = await self._frame(browser, context)
            try:
                return await download(frame, origin, self.agent)
            except ConnectionError:
                if self._frames.get(context) is frame:
                    del self._frames[context]
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")

    async def _frame(self, browser: Any, context: str) -> Frame:
        async with self._frame_lock:
            if (frame := self._frames.get(context)) is None:
                frame = self._frames[context] = await open_frame(browser, context)
            return frame

    def _landed(self, key: tuple[str, str], flight: asyncio.Future) -> None:
        if self._flights.get(key) is flight:
            del self._flights[key]
        if flight.cancelled() or flight.exception() is not None:
            return  # not cached: the next caller downloads again
        rules, ttl = flight.result()
        self._cache[key] = (_now() + ttl, rules)
        self._cache.move_to_end(key)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)


def of(browser: Any) -> Robots:
    """*browser*'s :class:`Robots` (a default one for a stand-in without it)."""
    robots = getattr(browser, "_robots", None)
    return robots if isinstance(robots, Robots) else Robots()


async def guard(tab: Tab, url: str, timeout: float) -> float:
    """Before a navigation of *tab* to *url*: the browser's check, within
    *timeout*; returns the time left for the navigation itself."""
    robots = of(tab._browser)
    if not robots.respect:
        return timeout
    loop = asyncio.get_running_loop()
    start = loop.time()
    try:
        await robots.check(tab, url, timeout)
    except NavigationTimeoutError:
        raise NavigationTimeoutError(url, "robots.txt", timeout) from None
    return max(timeout - (loop.time() - start), 0.01)


async def close_on_robots(tab: Tab, navigation: Any) -> None:
    """Await *navigation* of the new *tab*; if robots.txt refuses it, close the
    tab (nobody else holds it) and re-raise."""
    try:
        await navigation
    except RobotsDisallowedError:
        try:
            await tab._browser._close_tab(tab)
        except Exception:  # noqa: BLE001 — the refusal is what the caller needs
            logger.debug("Could not close a tab robots.txt refused", exc_info=True)
        raise

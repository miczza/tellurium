"""The browsers the server owns: sessions (named or throwaway), their tabs and
the ids the agent uses for them; plus the session-* and tab-* tools.

A named session is a :class:`tellurium.Session` under ``<home>/sessions/<name>``:
the same profile (cookies, storage) and seed come back the next time. Every
session is closed, and the named ones saved, by ``session-close`` or when the
server exits.
"""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import AsyncExitStack
from typing import Any

from tellurium.browser.browser import Browser
from tellurium.browser.tab import Tab
from tellurium.mcp import page_state
from tellurium.mcp.config import ServerConfig
from tellurium.mcp.results import Reply, ToolError
from tellurium.mcp.tool import Tool, param
from tellurium.session import Session

logger = logging.getLogger(__name__)

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_TEMP_PREFIX = "temp-"
# A tab's live state is a nicety in listings: never wait long for it.
_LIST_TIMEOUT = 2.0


class BrowserSession:
    """One browser: *session* is the :class:`Session` of a named one, else ``None``."""

    def __init__(self, session_id: str, browser: Browser, stack: AsyncExitStack, session=None):
        self.id = session_id
        self.browser = browser
        self.session: Session | None = session
        self._stack = stack

    @property
    def persistent(self) -> bool:
        return self.session is not None

    async def close(self) -> None:
        """Save a named session, then close its browser (both even on error)."""
        try:
            if self.session is not None:
                await asyncio.to_thread(self.session.save)
        finally:
            await self._stack.aclose()


class SessionPool:
    """Owns every browser the server opened; ``async with`` closes them all."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self._sessions: dict[str, BrowserSession] = {}
        self._tabs: dict[str, tuple[BrowserSession, Tab]] = {}
        self._lock = asyncio.Lock()  # one launch or close at a time: one profile, one Chrome
        self._next_temp = 0
        self._next_tab = 0

    async def __aenter__(self) -> SessionPool:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close_all()

    # -- sessions --------------------------------------------------------

    async def open(self, name: str | None) -> tuple[BrowserSession, bool]:
        """The session called *name* (a new throwaway one when ``None``), and
        whether this call opened it."""
        if name is not None:
            _check_name(name)
        async with self._lock:
            if name is not None and name in self._sessions:
                return self._sessions[name], False
            opened = await (self._launch_named(name) if name else self._launch_temp())
            self._sessions[opened.id] = opened
            return opened, True

    def _launch_options(self) -> dict[str, Any]:
        return {"headless": not self.config.headed, "stealth": True}

    async def _launch_temp(self) -> BrowserSession:
        stack = AsyncExitStack()
        try:
            browser = await Browser.launch(**self._launch_options())
            stack.push_async_callback(browser.close)
        except BaseException:
            await stack.aclose()
            raise
        self._next_temp += 1
        return BrowserSession(f"{_TEMP_PREFIX}{self._next_temp}", browser, stack)

    async def _launch_named(self, name: str) -> BrowserSession:
        path = str(self.config.sessions_dir / name)
        session = await asyncio.to_thread(Session, name, path=path)
        stack = AsyncExitStack()
        try:
            browser = await stack.enter_async_context(session.start(**self._launch_options()))
            await asyncio.to_thread(session.save)  # the seed survives a crash
        except BaseException:
            await stack.aclose()
            raise
        return BrowserSession(name, browser, stack, session)

    def get(self, session_id: str) -> BrowserSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            open_ids = ", ".join(self._sessions) or "none"
            raise ToolError(
                f"Unknown sessionId {session_id!r} (open: {open_ids}): see session-list"
            ) from None

    def sessions(self) -> list[BrowserSession]:
        return list(self._sessions.values())

    async def close(self, session_id: str) -> BrowserSession:
        async with self._lock:
            closing = self.get(session_id)
            del self._sessions[session_id]
            for tid in [t for t, (s, _) in self._tabs.items() if s is closing]:
                del self._tabs[tid]
            await closing.close()
            return closing

    async def close_all(self) -> None:
        """Close (and save) every session; one failing does not stop the others."""
        for session_id in list(self._sessions):
            try:
                await self.close(session_id)
            except Exception:  # noqa: BLE001 - shutdown: log and go on
                logger.exception("closing session %s failed", session_id)

    # -- tabs ------------------------------------------------------------

    def tabs(self, session: BrowserSession) -> list[tuple[str, Tab]]:
        """The open tabs of *session* with their ids; popups get one on sight."""
        mine = [(tid, tab) for tid, (s, tab) in self._tabs.items() if s is session]
        for tid, tab in mine:
            if tab.closed:
                del self._tabs[tid]
        out = []
        for tab in session.browser.tabs:
            if tab.closed:
                continue
            tid = next((t for t, seen in mine if seen is tab), None)
            out.append((tid or self._register(session, tab), tab))
        return out

    def _register(self, session: BrowserSession, tab: Tab) -> str:
        self._next_tab += 1
        tid = f"t{self._next_tab}"
        self._tabs[tid] = (session, tab)
        return tid

    def tab_id(self, session: BrowserSession, tab: Tab) -> str:
        return next(tid for tid, t in self.tabs(session) if t is tab)

    def tab(self, target_id: str) -> Tab:
        """The open tab *target_id*, else a :class:`ToolError` the agent can act on."""
        if target_id not in self._tabs:
            for session in self._sessions.values():
                self.tabs(session)  # a popup may have opened since
        entry = self._tabs.get(target_id)
        if entry is None or entry[1].closed:
            raise ToolError(f"Unknown or closed targetId {target_id!r}: see tab-list")
        return entry[1]

    def owner(self, target_id: str) -> BrowserSession:
        self.tab(target_id)
        return self._tabs[target_id][0]


def _check_name(name: str) -> None:
    if not _NAME.fullmatch(name) or re.fullmatch(rf"{_TEMP_PREFIX}\d+", name):
        raise ToolError(
            f"Invalid session name {name!r}: 1-64 letters, digits, '.', '_' or '-', "
            f"starting with a letter or digit, not '{_TEMP_PREFIX}<n>'"
        )


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


async def _tab_info(tid: str, session: BrowserSession, tab: Tab) -> dict[str, Any]:
    state = await page_state.read_or_none(tab, timeout=_LIST_TIMEOUT)
    url, title = (state.url, state.title) if state else (tab.url, tab.title)
    return {"targetId": tid, "sessionId": session.id, "url": url, "title": title}


async def _session_open(pool: SessionPool, args: dict[str, Any]) -> Reply:
    session, created = await pool.open(args.get("name"))
    tabs = pool.tabs(session)
    if not tabs:  # every tab was closed: give the agent one to work in
        await session.browser.new_tab()
        tabs = pool.tabs(session)
    tid = tabs[0][0]
    data = {
        "sessionId": session.id,
        "targetId": tid,
        "persistent": session.persistent,
        "created": created,
    }
    verb = "opened" if created else "already open:"
    kind = "named session" if session.persistent else "throwaway session"
    return Reply(f"{verb} {kind} {session.id}, tab {tid}", data)


async def _session_list(pool: SessionPool, args: dict[str, Any]) -> Reply:
    rows = [
        {
            "sessionId": s.id,
            "persistent": s.persistent,
            "tabs": [tid for tid, _ in pool.tabs(s)],
        }
        for s in pool.sessions()
    ]
    text = "\n".join(
        f"{r['sessionId']} ({'named' if r['persistent'] else 'throwaway'}): "
        f"{', '.join(r['tabs']) or 'no tabs'}"
        for r in rows
    )
    return Reply(text or "no open sessions", {"sessions": rows})


async def _session_close(pool: SessionPool, args: dict[str, Any]) -> Reply:
    closed = await pool.close(args["sessionId"])
    saved = " and saved" if closed.persistent else ""
    return Reply(f"closed{saved} {closed.id}", {"sessionId": closed.id, "saved": closed.persistent})


async def _tab_open(pool: SessionPool, args: dict[str, Any]) -> Reply:
    session = pool.get(args["sessionId"])
    tab = await session.browser.new_tab(args.get("url") or "about:blank")
    info = await _tab_info(pool.tab_id(session, tab), session, tab)
    return Reply(f"opened tab {info['targetId']} at {info['url']}", info)


async def _tab_list(pool: SessionPool, args: dict[str, Any]) -> Reply:
    wanted = [pool.get(args["sessionId"])] if "sessionId" in args else pool.sessions()
    rows = [await _tab_info(tid, s, tab) for s in wanted for tid, tab in pool.tabs(s)]
    text = "\n".join(f"{r['targetId']} [{r['sessionId']}] {r['title']} - {r['url']}" for r in rows)
    return Reply(text or "no open tabs", {"tabs": rows})


async def _tab_close(pool: SessionPool, args: dict[str, Any]) -> Reply:
    tab = pool.tab(args["targetId"])
    await tab.close()
    return Reply(f"closed tab {args['targetId']}", {"targetId": args["targetId"], "ok": True})


_SESSION_ID = param("string", "Session id from session-open or session-list.")

TOOLS = [
    Tool(
        "session-open",
        "Open a browser session and return its sessionId and first tab's targetId. "
        "With name, a saved identity (cookies, storage, fingerprint seed) that comes "
        "back next time; without, a throwaway one. Opening an open name returns it.",
        _session_open,
        {"name": param("string", "Saved session name, e.g. 'github'. Omit for throwaway.")},
        timeout=120.0,
    ),
    Tool("session-list", "List open sessions and their tab ids.", _session_list),
    Tool(
        "session-close",
        "Close a session and its browser; a named one is saved first.",
        _session_close,
        {"sessionId": _SESSION_ID},
        required=("sessionId",),
    ),
    Tool(
        "tab-open",
        "Open a new tab in a session (at url, else blank) and return its targetId.",
        _tab_open,
        {"sessionId": _SESSION_ID, "url": param("string", "Address to load.")},
        required=("sessionId",),
    ),
    Tool(
        "tab-list",
        "List open tabs (popups included) with url and title, of one session or all.",
        _tab_list,
        {"sessionId": _SESSION_ID},
    ),
    Tool("tab-close", "Close a tab.", _tab_close, page=True),
]

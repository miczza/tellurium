"""The MCP server: the tool set, the dispatch of a call, and how it is served.

The transport is a parameter of :func:`serve`: ``"stdio"`` (no port opened,
which suits the pipe-only design; one client, one session pool) or ``"http"``
(Streamable HTTP behind a token, one session pool per MCP client: see
:mod:`tellurium.mcp.http_transport`). The server itself does not depend on it.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import os
import select
import sys
from collections.abc import Awaitable, Callable, Iterable
from contextlib import AbstractAsyncContextManager, nullcontext
from typing import Any

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from tellurium import __version__
from tellurium.mcp import actions, pages, sessions
from tellurium.mcp.config import ServerConfig
from tellurium.mcp.results import explain, failure, success
from tellurium.mcp.sessions import SessionPool
from tellurium.mcp.tool import Tool
from tellurium.multiplexer import stop_signals

#: What stops the server like the client going away: kill, Ctrl-C, and on
#: Windows Ctrl-Break (SIGTERM is TerminateProcess there).
_STOP_NAMES = ("SIGTERM", "SIGINT", "SIGBREAK")

logger = logging.getLogger(__name__)

INSTRUCTIONS = """\
tellurium drives a real Chrome (stealth, human-like input by default).
1. session-open {name?}: a named session ('github') keeps its logins, storage and
   fingerprint across runs; without a name it is throwaway. It returns sessionId
   and the targetId of its first tab. Every page tool takes a targetId (from
   session-open, tab-open or tab-list).
2. navigate {targetId, url}: http(s), about:blank and data: only (file: and
   browser pages are refused unless the server runs with --allow-local-urls).
3. snapshot {targetId}: the page as an accessibility tree, one node per line,
   with [ref=eN] on what you can act on. Big page: interactive=true or
   selector='form'.
4. click / fill / select-option / check / hover / press / scroll / download
   {targetId, ref}. Actions return {ok, url, title, navigated}, not a snapshot:
   take a new snapshot when the page changed. A stale ref means exactly that.
5. get-text, screenshot, wait-for {text|ref|url} read without acting.
More tabs: tab-open, tab-list (popups show up there), tab-close.
session-close saves a named session; every session is saved when the server stops.
"""

# A transport serves *config* until its client goes or the event is set (it
# sets it too when it learns the client is gone); True if the event ended it.
Transport = Callable[[ServerConfig, asyncio.Event], Awaitable[bool]]
# The pool a tool call runs against, held for the duration of the call.
PoolFor = Callable[[Any], AbstractAsyncContextManager[Any]]
# How often the stdio transport checks that the client still reads its replies.
READER_POLL = 0.5


class StartupError(Exception):
    """The server cannot start as configured; the message says why."""


def build_tools(config: ServerConfig) -> list[Tool]:
    tools = [*sessions.TOOLS, *pages.TOOLS, *actions.TOOLS]
    if config.allow_eval:
        tools.append(pages.EVAL_TOOL)
    return tools


def build_server(
    pool: Any,
    tools: Iterable[Tool],
    *,
    use_pool: PoolFor | None = None,
    max_call: float | None = None,
) -> Server[Any]:
    """A low-level MCP server listing *tools* and running them against *pool*,
    or against the pool ``use_pool(ctx)`` picks for each request. *max_call*
    caps every tool's own timeout."""
    pool_for = use_pool or (lambda ctx: nullcontext(pool))
    by_name = {tool.name: tool for tool in tools}
    listing = types.ListToolsResult(
        tools=[
            types.Tool(name=t.name, description=t.description, input_schema=t.input_schema())
            for t in by_name.values()
        ]
    )

    async def list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        return listing

    async def call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        tool = by_name.get(params.name)
        if tool is None:
            return failure(f"Unknown tool {params.name!r}; tools: {', '.join(by_name)}")
        try:
            args = tool.check(params.arguments)
            async with pool_for(ctx) as pool:
                timeout = tool.timeout if max_call is None else min(tool.timeout, max_call)
                reply = await asyncio.wait_for(tool.handler(pool, args), timeout)
        except Exception as exc:  # noqa: BLE001 - every failure is a result, never a crash
            logger.debug("tool %s failed", tool.name, exc_info=True)
            return failure(explain(exc))
        return success(reply)

    return Server(
        "tellurium",
        version=__version__,
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def _stdio(server: Server[Any], stop: asyncio.Event) -> None:
    # Our own handle on the reply pipe, taken before the SDK moves fd 1 aside.
    watched = os.dup(sys.stdout.fileno())
    watcher = asyncio.ensure_future(_until_reader_gone(watched, stop))
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        watcher.cancel()
        os.close(watched)


async def _until_reader_gone(fd: int, stop: asyncio.Event) -> None:
    """Set *stop* once nobody reads the pipe *fd* writes to (a client that closed
    only its end of our stdout): replies could never arrive. Nothing is written:
    Linux's poll() reports POLLERR on the writing end, macOS's kqueue EV_EOF
    (its poll() reports nothing for a pipe)."""
    if not hasattr(select, "poll") and not hasattr(select, "kqueue"):
        return  # Windows: the next reply fails instead
    watch = _ReaderWatch(fd)
    try:
        while not watch.gone():
            await asyncio.sleep(READER_POLL)
    finally:
        watch.close()
    logger.warning("the client stopped reading replies: shutting down")
    stop.set()


class _ReaderWatch:
    """Whether the reader of the pipe *fd* writes to is gone, without waiting."""

    def __init__(self, fd: int) -> None:
        self._queue: Any = None
        self._poller: Any = None
        if sys.platform == "darwin" and hasattr(select, "kqueue"):
            self._queue = select.kqueue()
            change = select.kevent(fd, filter=select.KQ_FILTER_WRITE, flags=select.KQ_EV_ADD)
            self._queue.control([change], 0, 0)
        else:
            self._poller = select.poll()
            self._poller.register(fd, 0)  # POLLERR / POLLHUP / POLLNVAL always come

    def gone(self) -> bool:
        if self._queue is not None:
            events = self._queue.control(None, 1, 0)
            return any(event.flags & select.KQ_EV_EOF for event in events)
        return bool(self._poller.poll(0))

    def close(self) -> None:
        if self._queue is not None:
            self._queue.close()


async def _serve_stdio(config: ServerConfig, stop: asyncio.Event) -> bool:
    async with SessionPool(config) as pool:
        server = build_server(pool, build_tools(config))
        serving = asyncio.ensure_future(_stdio(server, stop))
        stopping = asyncio.ensure_future(stop.wait())
        try:
            await asyncio.wait({serving, stopping}, return_when=asyncio.FIRST_COMPLETED)
        except BaseException:
            serving.cancel()
            raise
        finally:
            stopping.cancel()
        if serving.done():
            serving.result()
            return False
    return True  # *serving* stays parked on its stdin read: see run()


async def _serve_http(config: ServerConfig, stop: asyncio.Event) -> bool:
    from tellurium.mcp import http_transport  # uvicorn only when HTTP is asked for

    return await http_transport.serve(config, stop)


TRANSPORTS: dict[str, Transport] = {"stdio": _serve_stdio, "http": _serve_http}


async def serve(
    config: ServerConfig, transport: str = "stdio", stop: asyncio.Event | None = None
) -> bool:
    """Serve until the client goes away or *stop* is set; then close every
    session, saving the named ones (also when cancelled). True if *stop* ended it."""
    return await TRANSPORTS[transport](config, stop or asyncio.Event())


def run(config: ServerConfig, transport: str = "stdio") -> None:
    """Blocking entry point of ``tellurium mcp``. SIGTERM, SIGINT and on Windows
    SIGBREAK (Ctrl-Break) close and save every session like the client closing
    stdin does, then end the process with 0.
    A configuration the server cannot start with ends it with a message."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    async def main() -> None:
        stop = asyncio.Event()
        # On Windows Ctrl-Break too: the way to ask it to stop from outside.
        release = stop_signals.catch(asyncio.get_running_loop(), stop.set, _STOP_NAMES)
        try:
            stopped = await serve(config, transport, stop)
        finally:
            release()  # a late signal cannot kill it while it exits
        if stopped and transport == "stdio":
            # The stdio transport reads stdin in a worker thread that no
            # cancellation reaches, so the loop could never finish; every
            # resource the server owns (browsers, profiles, pipes) is closed.
            gc.collect()  # what closed browsers leave to finalizers (stealth extension dirs)
            sys.stderr.flush()
            os._exit(0)

    try:
        asyncio.run(main())
    except StartupError as exc:
        print(f"tellurium mcp: {exc}", file=sys.stderr)
        sys.exit(2)

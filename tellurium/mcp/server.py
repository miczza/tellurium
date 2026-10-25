"""The MCP server: the tool set, the dispatch of a call, and how it is served.

The transport is a parameter of :func:`serve`: only ``"stdio"`` for now (no
port opened, which suits the pipe-only design); the server itself does not
depend on it.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import os
import select
import signal
import sys
from collections.abc import Awaitable, Callable, Iterable
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

# A transport serves *server* until its client goes; it sets the event when it
# learns the client is gone without the server loop noticing.
Transport = Callable[[Server[Any], asyncio.Event], Awaitable[None]]
# How often the stdio transport checks that the client still reads its replies.
READER_POLL = 0.5


def build_tools(config: ServerConfig) -> list[Tool]:
    tools = [*sessions.TOOLS, *pages.TOOLS, *actions.TOOLS]
    if config.allow_eval:
        tools.append(pages.EVAL_TOOL)
    return tools


def build_server(pool: Any, tools: Iterable[Tool]) -> Server[Any]:
    """A low-level MCP server listing *tools* and running them against *pool*."""
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
            reply = await asyncio.wait_for(tool.handler(pool, args), tool.timeout)
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
    only its end of our stdout): replies could never arrive. POSIX pipes report
    that as POLLERR on the writing end, without writing anything."""
    if not hasattr(select, "poll"):
        return  # Windows: the next reply fails instead
    poller = select.poll()
    poller.register(fd, 0)  # POLLERR / POLLHUP / POLLNVAL are always reported
    while not poller.poll(0):
        await asyncio.sleep(READER_POLL)
    logger.warning("the client stopped reading replies: shutting down")
    stop.set()


TRANSPORTS: dict[str, Transport] = {"stdio": _stdio}


async def serve(
    config: ServerConfig, transport: str = "stdio", stop: asyncio.Event | None = None
) -> bool:
    """Serve until the client goes away or *stop* is set; then close every
    session, saving the named ones (also when cancelled). True if *stop* ended it."""
    run_transport = TRANSPORTS[transport]
    stop = stop or asyncio.Event()
    async with SessionPool(config) as pool:
        server = build_server(pool, build_tools(config))
        serving = asyncio.ensure_future(run_transport(server, stop))
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


def run(config: ServerConfig, transport: str = "stdio") -> None:
    """Blocking entry point of ``tellurium mcp``. SIGTERM and SIGINT close and save
    every session like the client closing stdin does, then end the process."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    async def main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):  # Windows
                pass
        if await serve(config, transport, stop):
            # The stdio transport reads stdin in a worker thread that no
            # cancellation reaches, so the loop could never finish; every
            # resource the server owns (browsers, profiles, pipes) is closed.
            gc.collect()  # what closed browsers leave to finalizers (stealth extension dirs)
            sys.stderr.flush()
            os._exit(0)

    asyncio.run(main())

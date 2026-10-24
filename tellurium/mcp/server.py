"""The MCP server: the tool set, the dispatch of a call, and how it is served.

The transport is a parameter of :func:`serve`: only ``"stdio"`` for now (no
port opened, which suits the pipe-only design); the server itself does not
depend on it.
"""

from __future__ import annotations

import asyncio
import logging
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
   and the targetId of its first tab. Page tools all take that targetId.
2. navigate {targetId, url}.
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

Transport = Callable[[Server[Any]], Awaitable[None]]


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


async def _stdio(server: Server[Any]) -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


TRANSPORTS: dict[str, Transport] = {"stdio": _stdio}


async def serve(config: ServerConfig, transport: str = "stdio") -> None:
    """Serve until the client goes away; then close every session, saving the
    named ones (also when cancelled)."""
    run_transport = TRANSPORTS[transport]
    async with SessionPool(config) as pool:
        await run_transport(build_server(pool, build_tools(config)))


def run(config: ServerConfig, transport: str = "stdio") -> None:
    """Blocking entry point of ``tellurium mcp``. SIGTERM and SIGINT stop it the
    same way the client closing stdin does: sessions are closed and saved."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    async def main() -> None:
        task = asyncio.current_task()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, task.cancel)
            except (NotImplementedError, RuntimeError):  # Windows
                pass
        try:
            await serve(config, transport)
        except asyncio.CancelledError:
            pass

    asyncio.run(main())

"""Over HTTP no tool call may outlast the SDK client's 300 s read timeout:
the server caps every call, and refuses a download timeout that would."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from mcp import Client  # noqa: E402

from tellurium.mcp import actions  # noqa: E402
from tellurium.mcp.config import HTTP_CALL_MAX, HttpConfig, ServerConfig  # noqa: E402
from tellurium.mcp.results import Reply, ToolError  # noqa: E402
from tellurium.mcp.server import build_server, build_tools  # noqa: E402
from tellurium.mcp.tool import Tool  # noqa: E402


async def _slow(pool, args):
    await asyncio.sleep(5)
    return Reply("never")


async def test_max_call_caps_a_longer_tool_timeout():
    tools = [Tool("slow", "Slow.", _slow, timeout=60)]
    async with Client(build_server("p", tools, max_call=0.2)) as client:
        result = await client.call_tool("slow", {})
    assert result.is_error and "Timed out" in result.content[0].text


def test_the_http_cap_leaves_room_under_the_client_read_timeout():
    assert HTTP_CALL_MAX <= 240
    assert all(
        t.timeout <= 300 for t in build_tools(ServerConfig(home="x")) if t.name != "download"
    )


class _Pool:
    def __init__(self, http):
        self.config = ServerConfig(home="x", http=http)

    def tab(self, target_id):
        raise AssertionError("the timeout is checked first")


async def test_download_timeout_over_http_is_capped_with_a_clear_error():
    with pytest.raises(ToolError, match=f"at most {actions.DOWNLOAD_MAX_HTTP} seconds over HTTP"):
        await actions._download(
            _Pool(HttpConfig()), {"targetId": "t1", "ref": "e1", "timeout": 200}
        )
    assert 2 * actions.DOWNLOAD_MAX_HTTP + 20 <= HTTP_CALL_MAX


async def test_download_timeout_on_stdio_keeps_its_range():
    with pytest.raises(AssertionError, match="checked first"):
        await actions._download(_Pool(None), {"targetId": "t1", "ref": "e1", "timeout": 200})

"""The MCP server without Chrome: dispatch through a real in-process client,
the tool set, the CLI entry and how actions read where the page went."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import Client  # noqa: E402

from tellurium.browser.handles import StaleElementError  # noqa: E402
from tellurium.mcp import page_state  # noqa: E402
from tellurium.mcp.config import ServerConfig  # noqa: E402
from tellurium.mcp.results import Reply  # noqa: E402
from tellurium.mcp.server import INSTRUCTIONS, build_server, build_tools  # noqa: E402
from tellurium.mcp.tool import Tool, param  # noqa: E402


async def _echo(pool, args):
    return Reply(f"echo {args.get('word', '')}", {"word": args.get("word"), "pool": pool})


async def _stale(pool, args):
    raise StaleElementError("Ref @e3 belongs to a previous document")


async def _picture(pool, args):
    return Reply("a picture", {"ok": True}, image=b"\x89PNG fake")


async def _slow(pool, args):
    await asyncio.sleep(5)
    return Reply("never")


_TOOLS = [
    Tool("echo", "Echo a word.", _echo, {"word": param("string", "the word")}),
    Tool("stale", "Always stale.", _stale),
    Tool("picture", "An image.", _picture),
    Tool("slow", "Too slow.", _slow, timeout=0.2),
]


def _client() -> Client:
    # Entered inside each test: anyio cancel scopes must exit in the task that
    # entered them, which an async pytest fixture does not guarantee.
    return Client(build_server("the-pool", _TOOLS))


async def test_lists_tools_with_closed_schemas_and_instructions():
    async with _client() as client:
        listed = {t.name: t for t in (await client.list_tools()).tools}
        assert set(listed) == {"echo", "stale", "picture", "slow"}
        assert listed["echo"].input_schema["additionalProperties"] is False
        assert client.instructions == INSTRUCTIONS


async def test_success_is_text_plus_structured_content():
    async with _client() as client:
        result = await client.call_tool("echo", {"word": "hi"})
        assert not result.is_error
        assert result.content[0].text == "echo hi"
        assert result.structured_content == {"word": "hi", "pool": "the-pool"}


async def test_unknown_argument_is_an_error_result():
    async with _client() as client:
        result = await client.call_tool("echo", {"word": "hi", "loud": True})
        assert result.is_error
        assert "unknown argument 'loud'" in result.content[0].text


async def test_domain_error_becomes_an_actionable_message():
    async with _client() as client:
        result = await client.call_tool("stale", {})
        assert result.is_error
        assert "take a new snapshot" in result.content[0].text


async def test_image_content():
    async with _client() as client:
        result = await client.call_tool("picture", {})
        assert [c.type for c in result.content] == ["text", "image"]
        assert result.content[1].mime_type == "image/png"


async def test_tool_timeout_is_an_error_result_not_a_hang():
    async with _client() as client:
        result = await client.call_tool("slow", {})
        assert result.is_error and "Timed out" in result.content[0].text


async def test_unknown_tool():
    async with _client() as client:
        result = await client.call_tool("nope", {})
        assert result.is_error and "echo" in result.content[0].text


# --------------------------------------------------------------------------- #
# The real tool set
# --------------------------------------------------------------------------- #

_SPEC_TOOLS = {
    "session-open",
    "session-list",
    "session-close",
    "tab-open",
    "tab-list",
    "tab-close",
    "navigate",
    "snapshot",
    "click",
    "fill",
    "press",
    "select-option",
    "check",
    "hover",
    "scroll",
    "wait-for",
    "get-text",
    "screenshot",
    "download",
    "eval",
}


def test_tool_set_matches_the_spec(tmp_path: Path):
    tools = build_tools(ServerConfig(home=tmp_path))
    names = [t.name for t in tools]
    assert set(names) == _SPEC_TOOLS and len(names) == len(set(names)) <= 20
    assert all(re.fullmatch(r"[a-z]+(-[a-z]+)*", n) for n in names)
    session_tools = {"session-open", "session-list", "session-close", "tab-open", "tab-list"}
    for tool in tools:
        schema = tool.input_schema()
        assert schema["additionalProperties"] is False
        assert tool.page == (tool.name not in session_tools), tool.name
        if tool.page:
            assert schema["required"][0] == "targetId"


def test_eval_is_listed_only_when_allowed(tmp_path: Path):
    names = {t.name for t in build_tools(ServerConfig(home=tmp_path, allow_eval=False))}
    assert "eval" not in names and "click" in names


def test_cli_mcp_runs_stdio_with_the_options(monkeypatch, tmp_path):
    import tellurium.mcp.server as server
    from tellurium.cli import main

    seen = {}
    monkeypatch.setattr(server, "run", lambda config, transport: seen.update(c=config, t=transport))
    monkeypatch.setenv("TELLURIUM_HOME", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["tellurium", "mcp", "--headed"])
    main()
    assert seen["t"] == "stdio"
    assert seen["c"] == ServerConfig(home=tmp_path, headed=True, allow_eval=True)
    monkeypatch.setattr("sys.argv", ["tellurium", "mcp", "--allow-local-urls"])
    main()
    assert seen["c"].allow_local_urls is True and seen["c"].headed is False


# --------------------------------------------------------------------------- #
# Where the page went after an action
# --------------------------------------------------------------------------- #


class _FakeTab:
    """``eval`` answers from a script: a value, or an exception to raise."""

    url = "about:blank"

    def __init__(self, *answers):
        self.answers = list(answers)

    async def eval(self, expression, timeout=None):
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer


async def test_same_document_is_not_a_navigation():
    tab = _FakeTab(["http://a/", "A", 100.0, "complete"])
    before = await page_state.read(tab)
    after, navigated = await page_state.after_action(tab, before, settle=0)
    assert (after.url, after.title, navigated) == ("http://a/", "A", False)


async def test_new_document_is_a_navigation_waited_past_errors_and_loading():
    tab = _FakeTab(
        ["http://a/", "A", 100.0, "complete"],
        RuntimeError("Execution context was destroyed"),
        ["http://b/", "", 200.0, "loading"],
        ["http://b/", "B", 200.0, "complete"],
    )
    before = await page_state.read(tab)
    after, navigated = await page_state.after_action(tab, before, settle=0, poll=0)
    assert (after.url, after.title, navigated) == ("http://b/", "B", True)


async def test_unreadable_page_gives_up_at_the_deadline():
    tab = _FakeTab(["http://a/", "A", 100.0, "complete"], RuntimeError("gone"))
    before = await page_state.read(tab)
    after, navigated = await page_state.after_action(tab, before, settle=0, poll=0, wait=0.05)
    assert navigated is True and after.url == "about:blank"


# --------------------------------------------------------------------------- #
# The pool owns launches and closes in flight
# --------------------------------------------------------------------------- #


class _FakeSession:
    persistent = False

    def __init__(self, sid: str, close_delay: float = 0.0):
        self.id, self.close_delay, self.closed = sid, close_delay, False

    async def close(self):
        await asyncio.sleep(self.close_delay)
        self.closed = True


async def test_session_close_cut_by_its_timeout_keeps_closing(tmp_path):
    from tellurium.mcp.sessions import SessionPool

    pool = SessionPool(ServerConfig(home=tmp_path))
    slow = _FakeSession("x", close_delay=0.3)
    pool._sessions["x"] = slow
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(pool.close("x"), 0.05)
    assert pool.sessions() == [slow]  # still the pool's until it is closed
    await pool.close_all()
    assert slow.closed and pool.sessions() == []


async def test_close_all_waits_for_a_launch_in_flight(tmp_path, monkeypatch):
    from tellurium.mcp.sessions import SessionPool

    pool = SessionPool(ServerConfig(home=tmp_path))
    launched = _FakeSession("temp-1")

    async def slow_launch():
        await asyncio.sleep(0.2)
        return launched

    monkeypatch.setattr(pool, "_launch_temp", slow_launch)
    opening = asyncio.ensure_future(pool.open(None))
    await asyncio.sleep(0.05)
    await pool.close_all()
    assert launched.closed and pool.sessions() == []
    assert (await opening)[0] is launched
    with pytest.raises(Exception, match="shutting down"):
        await pool.open(None)


async def test_close_all_cancels_a_launch_that_hangs(tmp_path, monkeypatch):
    from tellurium.mcp.sessions import SessionPool

    pool = SessionPool(ServerConfig(home=tmp_path))
    rolled_back = asyncio.Event()

    async def hung_launch():
        try:
            await asyncio.sleep(60)
        finally:
            rolled_back.set()

    monkeypatch.setattr(pool, "_launch_temp", hung_launch)
    opening = asyncio.ensure_future(pool.open(None))
    await asyncio.sleep(0.05)
    await pool.close_all(launch_grace=0.05)
    assert rolled_back.is_set()
    with pytest.raises(asyncio.CancelledError):
        await opening


def test_tool_schemas_stay_small(tmp_path: Path):
    """What every agent pays in tokens on connect: at most shuttle's 7.6 KB."""
    import json

    from mcp import types

    tools = build_tools(ServerConfig(home=tmp_path))
    listed = [
        types.Tool(name=t.name, description=t.description, input_schema=t.input_schema())
        for t in tools
    ]
    dumped = json.dumps([t.model_dump(by_alias=True, exclude_none=True) for t in listed])
    print(f"tool schemas: {len(dumped)} bytes")
    assert len(dumped) <= 7600
    target_ids = {json.dumps(t.input_schema()["properties"]["targetId"]) for t in tools if t.page}
    assert target_ids == {'{"type": "string"}'}  # explained once, in the instructions

"""``tellurium mcp`` driven by the official MCP client over stdio, against
local fixtures with a real (headless) Chrome.

The first test is the whole loop of the spec's Esito 1: open a named session,
navigate, snapshot, fill and click by ref, download, close; then a new server
process reopens the same identity, and one that exits without session-close
still saves it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import Client, StdioServerParameters  # noqa: E402

from tests.integration.conftest import DOWNLOAD_BODY  # noqa: E402

_TELLURIUM = Path(sys.executable).with_name("tellurium")


def _server(home: Path) -> Client:
    params = StdioServerParameters(
        command=str(_TELLURIUM),
        args=["mcp"],
        env={**os.environ, "TELLURIUM_HOME": str(home)},
    )
    return Client(params)


async def _call(client: Client, tool: str, **args):
    result = await client.call_tool(tool, args)
    assert not result.is_error, f"{tool} {args}: {result.content[0].text}"
    return result


async def _error(client: Client, tool: str, **args) -> str:
    result = await client.call_tool(tool, args)
    assert result.is_error, f"{tool} {args} should fail: {result.content[0].text}"
    return result.content[0].text


def _ref(snapshot: str, role: str, name: str | None = None, nth: int = 0) -> str:
    label = rf' "{re.escape(name)}"' if name is not None else ""
    found = re.findall(rf"- {role}{label}[^\n]*\[ref=(e\d+)\]", snapshot)
    assert len(found) > nth, f"no {role} {name!r} in:\n{snapshot}"
    return found[nth]


async def _snapshot(client: Client, tid: str, **opts) -> str:
    return (await _call(client, "snapshot", targetId=tid, **opts)).content[0].text


async def _text(client: Client, tid: str) -> str:
    return (await _call(client, "get-text", targetId=tid)).content[0].text


def _seed(home: Path) -> int:
    return json.loads((home / "sessions" / "github" / "session.json").read_text())["seed"]


async def test_named_session_full_loop_and_reopen(local_server, tmp_path):
    home = tmp_path / "home"

    async with _server(home) as client:
        opened = (await _call(client, "session-open", name="github")).structured_content
        assert opened["persistent"] and opened["created"]
        sid, tid = opened["sessionId"], opened["targetId"]

        await _call(client, "navigate", targetId=tid, url=f"{local_server}/login.html")
        page = await _snapshot(client, tid, interactive=True)
        await _call(client, "fill", targetId=tid, ref=_ref(page, "textbox", nth=0), text="ada")
        await _call(client, "fill", targetId=tid, ref=_ref(page, "textbox", nth=1), text="pw")
        clicked = await _call(client, "click", targetId=tid, ref=_ref(page, "button", "Sign in"))
        assert clicked.structured_content["ok"] is True
        assert clicked.structured_content["navigated"] is False
        assert "logged in as ada" in await _text(client, tid)

        moved = await _call(client, "navigate", targetId=tid, url=f"{local_server}/dashboard.html")
        assert moved.structured_content["navigated"] is True
        assert moved.structured_content["title"] == "Dashboard"
        assert "welcome back" in await _text(client, tid)

        await _call(client, "navigate", targetId=tid, url=f"{local_server}/download.html")
        page = await _snapshot(client, tid)
        got = await _call(client, "download", targetId=tid, ref=_ref(page, "link", "Report"))
        saved = Path(got.structured_content["path"])
        assert saved.parent == home / "downloads" and saved.name == "report.csv"
        assert saved.read_bytes() == DOWNLOAD_BODY

        closed = await _call(client, "session-close", sessionId=sid)
        assert closed.structured_content["saved"] is True
        listed = await _call(client, "session-list")
        assert listed.structured_content["sessions"] == []
    seed = _seed(home)

    # A new server process: the same identity comes back.
    async with _server(home) as client:
        opened = (await _call(client, "session-open", name="github")).structured_content
        tid = opened["targetId"]
        await _call(client, "navigate", targetId=tid, url=f"{local_server}/dashboard.html")
        assert "welcome back" in await _text(client, tid)
        await _call(
            client,
            "eval",
            targetId=tid,
            expression="document.cookie = 'second=1; path=/; max-age=86400'",
        )
        # no session-close: the server saves it when the client goes away

    async with _server(home) as client:
        tid = (await _call(client, "session-open", name="github")).structured_content["targetId"]
        await _call(client, "navigate", targetId=tid, url=f"{local_server}/dashboard.html")
        cookies = await _call(client, "eval", targetId=tid, expression="document.cookie")
        assert "second=1" in cookies.structured_content["value"]
    assert _seed(home) == seed


async def test_actions_tabs_and_errors(local_server, tmp_path):
    async with _server(tmp_path) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert len(tools) == 20 and {"snapshot", "download", "eval"} <= tools
        assert "snapshot" in client.instructions

        opened = (await _call(client, "session-open")).structured_content
        assert opened["persistent"] is False and opened["sessionId"].startswith("temp-")
        sid, tid = opened["sessionId"], opened["targetId"]

        await _call(client, "navigate", targetId=tid, url=f"{local_server}/snapshot_form.html")
        page = await _snapshot(client, tid, selector="form")
        assert "Need help?" not in page  # only the form subtree
        await _call(client, "check", targetId=tid, ref=_ref(page, "checkbox"), checked=False)
        await _call(
            client, "select-option", targetId=tid, ref=_ref(page, "combobox"), value="English"
        )
        await _call(client, "hover", targetId=tid, ref=_ref(page, "button", "More options"))
        await _call(client, "scroll", targetId=tid, direction="down", amount=200, human=False)
        email = _ref(page, "textbox", "Email")
        await _call(client, "press", targetId=tid, ref=email, key="End")
        state = await _call(
            client,
            "eval",
            targetId=tid,
            expression="[remember.checked, lang.value, document.activeElement.id]",
        )
        assert state.structured_content["value"] == [False, "English", "email"]

        shot = await _call(client, "screenshot", targetId=tid)
        assert shot.content[1].type == "image" and shot.structured_content["bytes"] > 1000

        # A popup gets an id on sight; tabs open, list and close.
        await _call(client, "navigate", targetId=tid, url=f"{local_server}/opener.html")
        page = await _snapshot(client, tid)
        await _call(client, "click", targetId=tid, ref=_ref(page, "link", "Open popup"))
        await _call(client, "wait-for", targetId=tid, text="Open popup")
        extra = (await _call(client, "tab-open", sessionId=sid)).structured_content["targetId"]
        rows = (await _call(client, "tab-list", sessionId=sid)).structured_content["tabs"]
        assert len(rows) == 3 and extra in {r["targetId"] for r in rows}
        assert any(r["url"].endswith("/popup_target.html") for r in rows)
        await _call(client, "tab-close", targetId=extra)
        assert "tab-list" in await _error(client, "snapshot", targetId=extra)

        # Errors say what to do next.
        old = _ref(page, "link", "Open popup")
        await _call(client, "navigate", targetId=tid, url=f"{local_server}/login.html")
        assert "take a new snapshot" in await _error(client, "click", targetId=tid, ref=old)
        assert "unknown argument 'colour'" in await _error(
            client, "click", targetId=tid, ref=old, colour="red"
        )
        assert "take a snapshot" in await _error(client, "click", targetId=tid, ref="e999")
        page = await _snapshot(client, tid)
        heading = _ref(page, "heading", "Login")
        assert "cannot take keyboard focus" in await _error(
            client, "fill", targetId=tid, ref=heading, text="x"
        )
        nothing = await _error(client, "snapshot", targetId=tid, selector="#nope")
        assert "#nope" in nothing and "ref" not in nothing.lower()
        assert "Invalid URL" in await _error(client, "navigate", targetId=tid, url="notaurl")
        assert "session-list" in await _error(client, "tab-open", sessionId="nope")
        assert "Invalid session name" in await _error(client, "session-open", name="../x")
        missing = await _error(client, "wait-for", targetId=tid, text="never there", timeout=0.5)
        assert "Timed out" in missing


async def test_a_session_open_in_another_server_is_reported_as_such(tmp_path):
    async with _server(tmp_path) as first, _server(tmp_path) as second:
        await _call(first, "session-open", name="work")
        message = await _error(second, "session-open", name="work")
        assert "already open in another process" in message


def _rpc(proc: subprocess.Popen, message: dict) -> dict | None:
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline()) if "id" in message else None


def _chrome_using(path: Path) -> int:
    found = subprocess.run(["pgrep", "-fc", str(path)], capture_output=True, text=True)
    return int(found.stdout.strip() or 0)


@pytest.fixture
def short_tmp():
    """An empty TMPDIR for the server: short, Chrome's singleton socket path has a limit."""
    path = Path(tempfile.mkdtemp(prefix="tm", dir="/tmp"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _start(home: Path, tmp: Path) -> subprocess.Popen:
    proc = subprocess.Popen(
        [str(_TELLURIUM), "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "TELLURIUM_HOME": str(home), "TMPDIR": str(tmp)},
        text=True,
    )
    hello = {"protocolVersion": "2025-06-18", "capabilities": {}}
    hello["clientInfo"] = {"name": "test", "version": "1"}
    assert "result" in _rpc(proc, {"id": 1, "method": "initialize", "params": hello})
    _rpc(proc, {"method": "notifications/initialized"})
    return proc


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
        proc.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigterm_closes_and_saves_every_session(tmp_path, short_tmp):
    proc = _start(tmp_path, short_tmp)
    try:
        call = {"name": "session-open", "arguments": {"name": "work"}}
        opened = _rpc(proc, {"id": 2, "method": "tools/call", "params": call})
        assert opened["result"]["isError"] is False
        profile = tmp_path / "sessions" / "work"
        assert _chrome_using(profile) > 0

        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=30) == 0, proc.stderr.read()
        assert _chrome_using(profile) == 0
        assert (profile / "session.json").is_file()
        assert list(short_tmp.iterdir()) == []
    finally:
        _stop(proc)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.parametrize("delay", [0.05, 0.4, 1.0])
def test_sigterm_during_session_open_leaves_nothing_behind(tmp_path, short_tmp, delay):
    tmp = short_tmp
    proc = _start(tmp_path, tmp)
    try:
        call = {"name": "session-open", "arguments": {"name": "work"}}
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": call}) + "\n"
        )
        proc.stdin.flush()
        time.sleep(delay)  # Chrome is starting
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=60) == 0, proc.stderr.read()
        assert _chrome_using(tmp_path / "sessions" / "work") == 0
        assert list(tmp.iterdir()) == []
    finally:
        _stop(proc)

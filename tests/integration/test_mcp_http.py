"""``tellurium mcp --http`` as a real process, driven by the official MCP client
over Streamable HTTP and by raw HTTP requests, with a real (headless) Chrome
on local fixtures.

What the spec's Esito 2 promises: requests without the token, with a wrong one,
with the token in the URL or with any Origin (a web page) are refused; two clients do
not see each other's sessions or tabs; a named session is one client's at a
time; an idle client's sessions are closed and saved; eval is off on HTTP.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import signal
import stat
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

pytest.importorskip("mcp")

import httpx2  # noqa: E402
from mcp import Client  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402
from mcp.shared._httpx_utils import create_mcp_http_client  # noqa: E402
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS  # noqa: E402

_TELLURIUM = Path(sys.executable).with_name("tellurium")
_LISTENING = re.compile(r"listening on (http://\S+/mcp)")
_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": HANDSHAKE_PROTOCOL_VERSIONS[-1],
        "capabilities": {},
        "clientInfo": {"name": "raw", "version": "0"},
    },
}
_ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


class _Server:
    def __init__(self, proc: asyncio.subprocess.Process, url: str, home: Path):
        self.proc, self.url, self.home = proc, url, home
        self.stderr: list[str] = []

    @property
    def token(self) -> str:
        return (self.home / "mcp-token").read_text().strip()

    async def stop(self, timeout: float = 30) -> int:
        if self.proc.returncode is None:
            self.proc.send_signal(signal.SIGTERM)
        try:
            return await asyncio.wait_for(self.proc.wait(), timeout)
        except TimeoutError:
            self.proc.kill()
            await self.proc.wait()
            raise


async def _spawn(home: Path, *options: str) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        str(_TELLURIUM),
        "mcp",
        *options,
        env={**os.environ, "TELLURIUM_HOME": str(home)},
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )


@asynccontextmanager
async def _server(home: Path, *options: str) -> AsyncIterator[_Server]:
    proc = await _spawn(home, "--http", "127.0.0.1:0", *options)
    lines: list[str] = []
    url = None
    try:
        while url is None:
            line = await asyncio.wait_for(proc.stderr.readline(), 30)
            if not line:
                raise AssertionError(f"server exited: {''.join(lines)}")
            lines.append(line.decode())
            found = _LISTENING.search(lines[-1])
            url = found and found.group(1)
        server = _Server(proc, url, home)
        server.stderr = lines

        async def drain():
            async for raw in proc.stderr:
                lines.append(raw.decode())

        draining = asyncio.ensure_future(drain())
        try:
            yield server
        finally:
            code = await server.stop()
            await draining
            assert code == 0, "".join(lines)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


@asynccontextmanager
async def _client(server: _Server, token: str | None = None) -> AsyncIterator[Client]:
    headers = {"Authorization": f"Bearer {token or server.token}"}
    async with create_mcp_http_client(headers=headers) as http:
        async with Client(streamable_http_client(server.url, http_client=http)) as client:
            yield client


async def _call(client: Client, tool: str, **args):
    result = await client.call_tool(tool, args)
    assert not result.is_error, f"{tool} {args}: {result.content[0].text}"
    return result.structured_content


async def _error(client: Client, tool: str, **args) -> str:
    result = await client.call_tool(tool, args)
    assert result.is_error, f"{tool} {args} should fail: {result.content[0].text}"
    return result.content[0].text


async def _post(server: _Server, headers: dict[str, str], url: str | None = None):
    async with httpx2.AsyncClient() as http:
        return await http.post(url or server.url, json=_INIT, headers={**_ACCEPT, **headers})


# --------------------------------------------------------------------------- #
# The guard
# --------------------------------------------------------------------------- #


async def test_token_file_created_0600_and_requests_without_it_refused(tmp_path):
    async with _server(tmp_path / "home") as server:
        token_file = server.home / "mcp-token"
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
        token = server.token
        assert token not in "".join(server.stderr)  # never printed

        missing = await _post(server, {})
        assert missing.status_code == 401
        assert missing.headers["www-authenticate"] == "Bearer"
        assert "Authorization: Bearer" in missing.json()["error"]["message"]

        wrong = await _post(server, {"Authorization": f"Bearer {'x' * len(token)}"})
        assert wrong.status_code == 401

        in_url = await _post(server, {}, url=f"{server.url}?access_token={token}")
        assert in_url.status_code == 400
        in_url_too = await _post(
            server, {"Authorization": f"Bearer {token}"}, url=f"{server.url}?token={token}"
        )
        assert in_url_too.status_code == 400

        foreign = await _post(
            server, {"Authorization": f"Bearer {token}", "Origin": "https://evil.example"}
        )
        assert foreign.status_code == 403

        rebound = await _post(
            server, {"Authorization": f"Bearer {token}", "Host": "evil.example:80"}
        )
        assert rebound.status_code == 403

        good = await _post(server, {"Authorization": f"Bearer {token}"})
        assert good.status_code == 200
        assert good.headers.get("mcp-session-id")


async def test_official_client_with_a_wrong_token_cannot_connect(tmp_path):
    async with _server(tmp_path / "home") as server:
        with pytest.raises(Exception):  # noqa: B017 - the SDK's error type is not ours to pin
            async with _client(server, token="y" * 43) as client:
                await client.list_tools()


async def test_any_origin_is_refused(tmp_path):
    async with _server(tmp_path / "home") as server:
        for origin in ("http://app.example", server.url.removesuffix("/mcp")):
            refused = await _post(
                server, {"Authorization": f"Bearer {server.token}", "Origin": origin}
            )
            assert refused.status_code == 403
            assert "not web pages" in refused.json()["error"]["message"]


async def test_a_connection_that_never_finishes_its_headers_is_closed(tmp_path):
    """Slowloris: unauthenticated connections cannot be held open by dribbling."""
    from tellurium.mcp.http_transport import HEADER_TIMEOUT

    async with _server(tmp_path / "home") as server:
        host, port = server.url.removeprefix("http://").removesuffix("/mcp").rsplit(":", 1)
        reader, writer = await asyncio.open_connection(host, int(port))
        started = time.monotonic()
        writer.write(b"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1\r\n")
        await writer.drain()

        async def dribble():
            with contextlib.suppress(ConnectionError):
                while True:
                    await asyncio.sleep(0.5)
                    writer.write(b"X-Slow: 1\r\n")
                    await writer.drain()

        dribbling = asyncio.ensure_future(dribble())
        try:
            closed = await asyncio.wait_for(reader.read(), HEADER_TIMEOUT + 5)
        finally:
            dribbling.cancel()
            writer.close()
        assert time.monotonic() - started < HEADER_TIMEOUT + 3
        assert closed == b"" or closed.startswith(b"HTTP/1.1 4")


async def test_a_2026_envelope_is_told_to_use_the_handshake(tmp_path):
    """The stateless 2026-07-28 era has no MCP session: refused with the versions
    we speak, which is what makes the SDK fall back to initialize."""
    probe = {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}}
    async with _server(tmp_path / "home") as server, httpx2.AsyncClient() as http:
        headers = {**_ACCEPT, "Authorization": f"Bearer {server.token}"}
        reply = await http.post(
            server.url, json=probe, headers={**headers, "MCP-Protocol-Version": "2026-07-28"}
        )
        assert reply.status_code == 400
        error = reply.json()["error"]
        assert error["code"] == -32022
        assert error["data"]["supported"] == list(HANDSHAKE_PROTOCOL_VERSIONS)
        async with _client(server) as client:  # the SDK's default mode probes first
            assert client.protocol_version == HANDSHAKE_PROTOCOL_VERSIONS[-1]


async def test_screenshot_over_the_cap_through_the_client(local_server, tmp_path):
    async with _server(tmp_path / "home") as server, _client(server) as client:
        tid = (await _call(client, "session-open"))["targetId"]
        await _call(client, "navigate", targetId=tid, url=f"{local_server}/noise.html")
        for _ in range(50):
            tabs = (await _call(client, "tab-list"))["tabs"]
            if tabs[0]["title"] == "Noise ready":
                break
            await asyncio.sleep(0.1)
        result = await client.call_tool("screenshot", {"targetId": tid, "fullPage": True})
        assert not result.is_error, result.content[0].text
        image = result.content[1]
        assert image.mime_type == "image/jpeg"
        assert len(image.data) <= 5 * 1024 * 1024  # base64, as the client receives it
        assert "over the 5.0 MB cap" in result.content[0].text
        assert result.structured_content["format"] == "jpeg"


async def _dribbler(server: _Server, headers: str, count: int):
    """*count* connections that send a request head promising a huge body, then
    one byte of it every 2 s. Returns, per connection, what the server sent and
    when it closed (None: still open at the end)."""
    from tellurium.mcp.http_transport import BODY_TIMEOUT

    host, port = server.url.removeprefix("http://").removesuffix("/mcp").rsplit(":", 1)
    head = (
        f"POST /mcp HTTP/1.1\r\nHost: {host}:{port}\r\nContent-Type: application/json\r\n"
        f"Accept: application/json, text/event-stream\r\n{headers}"
        "Content-Length: 1000000000\r\n\r\n{"
    ).encode()

    async def one():
        reader, writer = await asyncio.open_connection(host, int(port))
        started = time.monotonic()
        writer.write(head)

        async def dribble():
            with contextlib.suppress(ConnectionError, OSError):
                while True:
                    await writer.drain()
                    await asyncio.sleep(2)
                    writer.write(b" ")

        dribbling = asyncio.ensure_future(dribble())
        try:
            got = await asyncio.wait_for(reader.read(), BODY_TIMEOUT + 6)
            return got, time.monotonic() - started
        except TimeoutError:
            return b"", None
        finally:
            dribbling.cancel()
            writer.close()

    return await asyncio.gather(*(one() for _ in range(count)))


async def test_refused_connections_are_closed_and_cannot_starve_the_server(tmp_path):
    """99 tokenless clients dribbling a body (one under the concurrency limit)
    are answered 401 and dropped at once; a client with the token still gets in."""
    async with _server(tmp_path / "home") as server:
        flood = asyncio.ensure_future(_dribbler(server, "", 99))
        await asyncio.sleep(1)
        async with _client(server) as client:
            assert (await _call(client, "session-list"))["sessions"] == []
        for got, closed_after in await flood:
            assert got.startswith(b"HTTP/1.1 401"), got[:80]
            assert b"connection: close" in got.lower()
            assert closed_after is not None and closed_after < 3


async def test_a_body_that_never_ends_is_cut_at_the_deadline(tmp_path):
    from tellurium.mcp.http_transport import BODY_TIMEOUT

    async with _server(tmp_path / "home") as server:
        auth = f"Authorization: Bearer {server.token}\r\n"
        ((got, closed_after),) = await _dribbler(server, auth, 1)
        assert closed_after is not None and closed_after < BODY_TIMEOUT + 3
        assert not got.startswith(b"HTTP/1.1 2")


async def test_mute_sockets_reopened_in_a_loop_do_not_lock_out_the_token(tmp_path):
    """Connections that never send a request are only closed by the header
    deadline; however many of them come and go, they take no place of the
    clients that passed the guard."""
    from tellurium.mcp.http_transport import CONCURRENCY

    async with _server(tmp_path / "home") as server:
        host, port = server.url.removeprefix("http://").removesuffix("/mcp").rsplit(":", 1)
        stop = asyncio.Event()

        async def mute():
            while not stop.is_set():
                with contextlib.suppress(OSError):
                    reader, writer = await asyncio.open_connection(host, int(port))
                    with contextlib.suppress(TimeoutError, OSError):
                        await asyncio.wait_for(reader.read(), 0.5)
                    writer.close()

        mutes = [asyncio.ensure_future(mute()) for _ in range(CONCURRENCY)]
        try:
            await asyncio.sleep(1)
            async with _client(server) as client:
                for _ in range(5):
                    assert (await _call(client, "session-list"))["sessions"] == []
                    await asyncio.sleep(0.5)
        finally:
            stop.set()
            await asyncio.gather(*mutes)


async def test_eval_is_off_on_http_unless_allowed(tmp_path):
    async with _server(tmp_path / "home") as server, _client(server) as client:
        assert client.protocol_version in HANDSHAKE_PROTOCOL_VERSIONS  # an MCP session
        names = {t.name for t in (await client.list_tools()).tools}
        assert "eval" not in names and "navigate" in names
    async with _server(tmp_path / "home", "--allow-eval") as server, _client(server) as client:
        assert "eval" in {t.name for t in (await client.list_tools()).tools}


async def test_loose_token_file_stops_the_server(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    loose = home / "mcp-token"
    loose.write_text("A" * 43)
    loose.chmod(0o644)
    proc = await _spawn(home, "--http", "127.0.0.1:0")
    _, err = await asyncio.wait_for(proc.communicate(), 30)
    assert proc.returncode == 2
    assert b"chmod 600" in err


async def test_non_loopback_bind_needs_a_flag(tmp_path):
    proc = await _spawn(tmp_path / "home", "--http", "0.0.0.0:0")
    _, err = await asyncio.wait_for(proc.communicate(), 30)
    assert proc.returncode == 2
    assert b"--allow-remote" in err


# --------------------------------------------------------------------------- #
# One browser per client
# --------------------------------------------------------------------------- #


async def test_two_clients_do_not_see_each_other(local_server, tmp_path):
    async with _server(tmp_path / "home") as server:
        async with _client(server) as a, _client(server) as b:
            opened = await _call(a, "session-open")
            sid, tid = opened["sessionId"], opened["targetId"]
            await _call(a, "navigate", targetId=tid, url=f"{local_server}/basic.html")

            assert (await _call(b, "session-list"))["sessions"] == []
            assert (await _call(b, "tab-list"))["tabs"] == []
            assert "Unknown or closed targetId" in await _error(b, "snapshot", targetId=tid)
            assert "Unknown sessionId" in await _error(b, "session-close", sessionId=sid)
            assert "Unknown sessionId" in await _error(b, "tab-open", sessionId=sid)

            await _call(b, "session-open")  # ids are per client: b's may spell like a's
            b_tabs = (await _call(b, "tab-list"))["tabs"]
            assert len(b_tabs) == 1 and "basic.html" not in b_tabs[0]["url"]
            a_tabs = (await _call(a, "tab-list"))["tabs"]
            assert len(a_tabs) == 1 and a_tabs[0]["url"].endswith("/basic.html")

            await _call(a, "session-open", name="github")
            taken = await _error(b, "session-open", name="github")
            assert "already open by another MCP client" in taken
            await _call(a, "session-close", sessionId="github")
            reopened = await _call(b, "session-open", name="github")
            assert reopened["created"] is True


class _Raw:
    """An MCP session spoken by hand, so the test knows its Mcp-Session-Id."""

    def __init__(self, server: _Server, http: httpx2.AsyncClient):
        self.server, self.http, self.id, self._next = server, http, "", 1

    def _headers(self) -> dict[str, str]:
        auth = {"Authorization": f"Bearer {self.server.token}", **_ACCEPT}
        return {**auth, "Mcp-Session-Id": self.id} if self.id else auth

    async def start(self) -> _Raw:
        reply = await self.http.post(self.server.url, json=_INIT, headers=self._headers())
        self.id = reply.headers["mcp-session-id"]
        note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        await self.http.post(self.server.url, json=note, headers=self._headers())
        return self

    async def call(self, tool: str, **args) -> dict:
        self._next += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._next,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }
        reply = await self.http.post(self.server.url, json=body, headers=self._headers())
        text = reply.text
        if "text/event-stream" in reply.headers.get("content-type", ""):
            data = [ln[5:] for ln in text.splitlines() if ln.startswith("data:") and ln[5:].strip()]
            text = data[-1]
        result = json.loads(text)["result"]
        assert not result.get("isError"), result
        return result["structuredContent"]


async def test_a_delete_naming_two_sessions_is_refused_and_touches_neither(local_server, tmp_path):
    async with _server(tmp_path / "home") as server, httpx2.AsyncClient(timeout=60) as http:
        a, b = await _Raw(server, http).start(), await _Raw(server, http).start()
        await a.call("session-open")
        headers = [
            ("Authorization", f"Bearer {server.token}"),
            ("Mcp-Session-Id", b.id),
            ("Mcp-Session-Id", a.id),
        ]
        refused = await http.request("DELETE", server.url, headers=headers)
        assert refused.status_code == 400
        assert len((await a.call("session-list"))["sessions"]) == 1  # a's Chrome lives on
        assert (await b.call("session-list"))["sessions"] == []


async def test_browsers_are_capped_per_client_and_per_server(tmp_path):
    options = ("--max-sessions-per-client", "1", "--max-sessions", "2")
    async with _server(tmp_path / "home", *options) as server:
        async with _client(server) as a, _client(server) as b, _client(server) as c:
            await _call(a, "session-open")
            assert "most allowed per client" in await _error(a, "session-open")
            await _call(b, "session-open")
            assert "server already runs 2 sessions" in await _error(c, "session-open")
            sid = (await _call(a, "session-list"))["sessions"][0]["sessionId"]
            await _call(a, "session-close", sessionId=sid)
            await _call(c, "session-open")  # a's place is free again


async def _open_when_free(client: Client, name: str, within: float = 20):
    """session-open *name* as soon as the client holding it has let it go."""
    deadline = time.monotonic() + within
    while True:
        result = await client.call_tool("session-open", {"name": name})
        if not result.is_error:
            return result.structured_content
        assert "another MCP client" in result.content[0].text, result.content[0].text
        assert time.monotonic() < deadline, f"{name} was never released"
        await asyncio.sleep(0.3)


async def test_a_client_that_disconnects_has_its_browsers_closed(local_server, tmp_path):
    async with _server(tmp_path / "home") as server:
        async with _client(server) as a:
            await _call(a, "session-open", name="github")
        # Its MCP session ended (DELETE on close): the name is free again.
        async with _client(server) as b:
            assert (await _open_when_free(b, "github"))["created"] is True


async def test_idle_client_sessions_are_closed_and_saved(local_server, tmp_path):
    async with _server(tmp_path / "home", "--idle-timeout", "2", "--allow-eval") as server:
        async with _client(server) as a, _client(server) as b:
            tid = (await _call(a, "session-open", name="github"))["targetId"]
            await _call(a, "navigate", targetId=tid, url=f"{local_server}/basic.html")
            await _call(
                a, "eval", targetId=tid, expression="document.cookie = 'kept=1; max-age=86400'"
            )
            # No call from a from now on (any call would be activity).
            opened = await _open_when_free(b, "github")
            await _call(
                b, "navigate", targetId=opened["targetId"], url=f"{local_server}/basic.html"
            )
            cookies = await _call(
                b, "eval", targetId=opened["targetId"], expression="document.cookie"
            )
            assert "kept=1" in cookies["value"]  # closed *and saved* by the idle timeout
            # a is still connected: its old session is gone, it can open a new one.
            assert (await _call(a, "session-list"))["sessions"] == []
            assert (await _call(a, "session-open"))["created"] is True


async def test_sigterm_closes_saves_and_exits(local_server, tmp_path):
    home = tmp_path / "home"
    async with _server(home) as server:
        client = _client(server)
        a = await client.__aenter__()
        await _call(a, "session-open", name="github")
        started = time.monotonic()
        assert await server.stop() == 0
        assert time.monotonic() - started < 20
        with contextlib.suppress(Exception):  # the server is gone: its DELETE fails
            await client.__aexit__(None, None, None)
    assert (home / "sessions" / "github" / "session.json").exists()


async def test_readme_python_client_example_runs(local_server, tmp_path):
    """The HTTP client example in the README, against a real server."""
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text()
    section = readme[readme.index("### Over HTTP (`tellurium mcp --http`)") :]
    example = re.search(r"```python\n(.*?)```", section, re.S).group(1)
    async with _server(tmp_path / "home") as server:
        script = (
            example.replace('"http://127.0.0.1:8765/mcp"', repr(server.url))
            .replace(
                'Path.home() / ".tellurium" / "mcp-token"',
                f"Path({str(server.home / 'mcp-token')!r})",
            )
            .replace('"https://example.com"', repr(f"{local_server}/basic.html"))
        )
        assert script != example and server.url in script
        (tmp_path / "example.py").write_text(script)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(tmp_path / "example.py"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), 60)
        assert proc.returncode == 0, err.decode()
        assert "[ref=" in out.decode() or "heading" in out.decode(), out.decode()

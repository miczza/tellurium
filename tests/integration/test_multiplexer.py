"""The multiplexer with stock Chrome and raw WebSocket clients: CDP round trip,
id remapping, the queue, one identity per connection, crash and hang repair,
shutdown with nothing left behind, and access refused before any upgrade."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
from urllib.parse import quote

import pytest

pytest.importorskip("websockets")

from websockets.asyncio.client import connect  # noqa: E402
from websockets.exceptions import ConnectionClosed, InvalidStatus  # noqa: E402

from tellurium import Multiplexer  # noqa: E402
from tellurium.browser.launcher import find_chrome  # noqa: E402
from tellurium.browser.raw_chrome import RawChrome  # noqa: E402
from tellurium.multiplexer import health  # noqa: E402
from tellurium.multiplexer import multiplexer as multiplexer_module  # noqa: E402
from tellurium.multiplexer import pool as pool_module  # noqa: E402
from tellurium.multiplexer import server as server_module  # noqa: E402
from tellurium.multiplexer.own_session import CommandError  # noqa: E402
from tellurium.multiplexer.relay import Relay  # noqa: E402
from tests.integration.test_authenticated_proxy import (  # noqa: E402, F401 - a fixture
    GOOD_AUTH,
    PASSWORD,
    USER,
    FakeProxy,
    tls_context,
)
from tests.integration.test_raw_chrome import (  # noqa: E402, F401 - private_tempdir is autouse
    _alive,
    _cmdline,
    _descendants,
    _profiles,
    _wait_until,
    private_tempdir,
)

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="uses /proc to observe processes"
)


@pytest.fixture(autouse=True)
def token_file(tmp_path, monkeypatch):
    path = tmp_path / "home" / "multiplex-token"
    monkeypatch.setattr(multiplexer_module, "TOKEN_FILE", path)
    return path


@contextlib.asynccontextmanager
async def serving(size: int = 1, **options):
    mux = Multiplexer(size, **{"geoip": False, **options})
    task = asyncio.ensure_future(mux.serve("127.0.0.1", 0))
    try:
        await _wait_until(lambda: mux.url is not None or task.done(), 30)
        if task.done():
            task.result()
        yield mux
    finally:
        task.cancel()
        await asyncio.wait([task])


def _port(mux: Multiplexer) -> int:
    return int(mux.url.rsplit(":", 1)[1])


def _client(mux: Multiplexer, path: str = "/devtools/browser/any", **kw):
    return connect(
        f"ws://127.0.0.1:{_port(mux)}{path}",
        additional_headers={"Authorization": f"Bearer {mux.token}"},
        max_size=None,
        open_timeout=90,
        **kw,
    )


async def _cdp(ws, id: int, method: str, params: dict | None = None, session: str = "") -> dict:
    """One command; events in between are dropped."""
    message = {"id": id, "method": method, "params": params or {}}
    if session:
        message["sessionId"] = session
    await ws.send(json.dumps(message))

    async def reply() -> dict:
        while True:
            answer = json.loads(await ws.recv())
            if answer.get("id") == id:
                return answer

    return await asyncio.wait_for(reply(), 20)


async def _closed(ws, timeout: float = 30.0) -> tuple[int | None, str]:
    """Read until the server closes *ws*: its close code and reason."""

    async def drain() -> ConnectionClosed:
        try:
            while True:
                await ws.recv()
        except ConnectionClosed as exc:
            return exc

    closed = await asyncio.wait_for(drain(), timeout)
    if closed.rcvd is None:
        return None, ""
    return closed.rcvd.code, closed.rcvd.reason


async def _http(
    port: int,
    target: str = "/json/version",
    headers: list[tuple[str, str]] | None = None,
    upgrade: bool = False,
) -> tuple[int, dict, bytes]:
    """A raw HTTP/1.1 GET with exactly *headers*: status, headers, body."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(_request(target, headers, upgrade))
        status = await asyncio.wait_for(reader.readline(), 90)
        found = {}
        while (line := await reader.readline()) not in (b"\r\n", b""):
            name, _, value = line.decode().partition(":")
            found[name.strip().lower()] = value.strip()
        body = await reader.readexactly(int(found.get("content-length", "0")))
        return int(status.split()[1]), found, body
    finally:
        writer.close()


def _request(target: str, headers: list[tuple[str, str]] | None, upgrade: bool) -> bytes:
    lines = [f"GET {target} HTTP/1.1", *(f"{k}: {v}" for k, v in headers or [])]
    if upgrade:
        lines += [
            "Upgrade: websocket",
            "Connection: Upgrade",
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
            "Sec-WebSocket-Version: 13",
        ]
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


def _good(mux: Multiplexer) -> list[tuple[str, str]]:
    return [("Host", f"127.0.0.1:{_port(mux)}"), ("Authorization", f"Bearer {mux.token}")]


def _pids(mux: Multiplexer) -> list[int]:
    return [s["pid"] for s in mux.status()["slots"] if s["pid"]]


# --------------------------------------------------------------------------- #
# CDP through the relay
# --------------------------------------------------------------------------- #


async def test_json_version_and_a_cdp_round_trip_on_a_flat_session(local_server):
    async with serving() as mux:
        status, headers, body = await _http(_port(mux), "/json/version/", _good(mux))
        assert status == 200 and headers["content-type"].startswith("application/json")
        version = json.loads(body)
        assert set(version) == {
            "Browser",
            "Protocol-Version",
            "User-Agent",
            "V8-Version",
            "WebKit-Version",
            "webSocketDebuggerUrl",
        }
        assert "Chrome" in version["Browser"] and version["Protocol-Version"] == "1.3"
        assert version["webSocketDebuggerUrl"].startswith(
            f"ws://127.0.0.1:{_port(mux)}/devtools/browser/"
        )
        assert (await _http(_port(mux), "/json/list", _good(mux)))[0] == 404

        async with connect(
            version["webSocketDebuggerUrl"],
            additional_headers={"Authorization": f"Bearer {mux.token}"},
            max_size=None,
        ) as ws:
            created = await _cdp(ws, 1, "Target.createTarget", {"url": "about:blank"})
            target = created["result"]["targetId"]
            attached = await _cdp(
                ws, 2, "Target.attachToTarget", {"targetId": target, "flatten": True}
            )
            session = attached["result"]["sessionId"]
            await _cdp(ws, 3, "Page.enable", session=session)
            await _cdp(
                ws, 4, "Page.navigate", {"url": f"{local_server}/basic.html"}, session=session
            )

            async def loaded() -> dict:
                while True:
                    event = json.loads(await ws.recv())
                    if event.get("method") == "Page.loadEventFired":
                        return event

            event = await asyncio.wait_for(loaded(), 20)
            assert event["sessionId"] == session  # events pass with their sessionId
            title = await _cdp(
                ws, 5, "Runtime.evaluate", {"expression": "document.title"}, session=session
            )
            assert title["sessionId"] == session
            assert title["result"]["result"]["value"]
        assert mux.status()["connections"] == 1


async def test_client_ids_are_remapped_and_probes_stay_invisible(monkeypatch):
    monkeypatch.setattr(health, "INTERVAL", 0.1)
    async with serving() as mux, _client(mux) as ws:
        sent = [7, 7, 10**12, -3, 0]
        for id in sent:
            await ws.send(json.dumps({"id": id, "method": "Browser.getVersion"}))
        got = []
        while len(got) < len(sent):
            message = json.loads(await asyncio.wait_for(ws.recv(), 10))
            assert "id" in message, message
            got.append(message["id"])
            assert "product" in message["result"]
        assert sorted(got) == sorted(sent)
        # Health probes keep going on the same pipe: none of their replies leaks.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.recv(), 1.0)


@pytest.mark.parametrize(
    "message",
    ["not json", '{"method": "Browser.getVersion"}', '{"id": true}', "[1]", "[" * 200_000],
    ids=["text", "no-id", "bool-id", "list", "nested"],
)
async def test_a_message_without_an_integer_id_closes_with_1007(message):
    async with serving() as mux, _client(mux) as ws:
        await ws.send(message)
        code, reason = await _closed(ws)
        assert code == 1007 and "integer id" in reason


# --------------------------------------------------------------------------- #
# The queue, and one identity per connection
# --------------------------------------------------------------------------- #


async def test_four_clients_four_chromes_the_fifth_waits_then_503():
    async with serving(4, acquire_timeout=4) as mux:
        async with contextlib.AsyncExitStack() as stack:
            clients = await asyncio.gather(
                *(stack.enter_async_context(_client(mux)) for _ in range(4))
            )
            pids = _pids(mux)
            assert len(set(pids)) == 4 and mux.status()["clients"] == 4

            fifth = asyncio.ensure_future(stack.enter_async_context(_client(mux)))
            assert await _wait_until(lambda: mux.status()["queue"] == 1, 5)
            await asyncio.sleep(0.5)
            assert not fifth.done()
            await clients[0].close()
            ws5 = await asyncio.wait_for(fifth, 30)
            assert (await _cdp(ws5, 1, "Browser.getVersion"))["result"]
            assert pids[0] not in _pids(mux)

            loop = asyncio.get_running_loop()
            start = loop.time()
            with pytest.raises(InvalidStatus) as refused:
                async with _client(mux):
                    pass
            assert refused.value.response.status_code == 503
            assert 3.5 < loop.time() - start < 15
            assert mux.status()["queue"] == 0


async def test_each_connection_gets_a_new_seed_and_the_next_proxy():
    """Patched engine flags on the stock binary: the seed shows on the command line."""
    stock = await find_chrome()
    proxies = ["http://127.0.0.1:18081", "http://user:secret@127.0.0.1:18082"]
    async with serving(2, proxies=proxies, browser="patched", executable=stock) as mux:
        seen = []
        for _ in range(3):
            async with _client(mux) as ws:
                await _cdp(ws, 1, "Browser.getVersion")
                (slot,) = [s for s in mux.status()["slots"] if s["state"] == "busy"]
                line = _cmdline(slot["pid"])
                assert f"--fingerprint={slot['seed']}" in line
                assert "--remote-debugging-pipe" in line
                assert not [a for a in line if "remote-debugging-port" in a]
                assert "secret" not in json.dumps(mux.status())
                seen.append((slot["pid"], slot["seed"], slot["proxy"], line))
        assert len({pid for pid, *_ in seen}) == 3
        assert len({seed for _, seed, *_ in seen}) == 3
        assert [proxy for _, _, proxy, _ in seen] == [
            "http://127.0.0.1:18081",
            "http://127.0.0.1:18082",
            "http://127.0.0.1:18081",
        ]
        assert "--proxy-server=http://127.0.0.1:18081" in seen[0][3]
        # The proxy with credentials sits behind a local forwarder.
        assert not [a for a in seen[1][3] if "18082" in a or "secret" in a]
        for pid, *_ in seen:
            assert await _wait_until(lambda pid=pid: not _alive(pid))


# --------------------------------------------------------------------------- #
# Repair
# --------------------------------------------------------------------------- #


async def test_a_killed_chrome_closes_its_client_with_1011_and_the_place_recovers():
    async with serving() as mux:
        async with _client(mux) as ws:
            await _cdp(ws, 1, "Browser.getVersion")
            (pid,) = _pids(mux)
            os.kill(pid, signal.SIGKILL)
            code, reason = await _closed(ws)
            assert code == 1011 and "exited" in reason
        async with _client(mux) as ws:
            assert (await _cdp(ws, 1, "Browser.getVersion"))["result"]
            assert _pids(mux) != [pid]
        status = mux.status()
        assert status["crashes"] == 1 and status["slots"][0]["restarts"] == 1


async def test_a_stopped_chrome_is_killed_and_replaced_with_or_without_client(monkeypatch):
    monkeypatch.setattr(health, "INTERVAL", 0.3)
    monkeypatch.setattr(health, "TIMEOUT", 0.7)
    async with serving(1, warm=1) as mux:
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "ready", 30)
        (warm_pid,) = _pids(mux)
        os.kill(warm_pid, signal.SIGSTOP)
        assert await _wait_until(lambda: not _alive(warm_pid), 15)
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "ready", 30)
        assert mux.status()["hangs"] == 1

        async with _client(mux) as ws:
            await _cdp(ws, 1, "Browser.getVersion")
            (pid,) = _pids(mux)
            os.kill(pid, signal.SIGSTOP)
            code, reason = await _closed(ws)
            assert code == 1011 and "health probes" in reason
            assert await _wait_until(lambda: not _alive(pid), 15)
        async with _client(mux) as ws:
            assert (await _cdp(ws, 1, "Browser.getVersion"))["result"]
        assert mux.status()["hangs"] == 2


async def test_browser_close_from_the_client_ends_it_normally():
    async with serving() as mux:
        async with _client(mux) as ws:
            (pid,) = _pids(mux)
            await ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
            code, _ = await _closed(ws)
            assert code == 1000
        assert await _wait_until(lambda: not _alive(pid))
        # Asked for by the client: neither a crash nor a restart; the place is idle again.
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "idle", 10)
        status = mux.status()
        assert status["crashes"] == 0 and status["slots"][0]["restarts"] == 0
        async with _client(mux) as ws:
            assert (await _cdp(ws, 2, "Browser.getVersion"))["result"]


# --------------------------------------------------------------------------- #
# Shutdown
# --------------------------------------------------------------------------- #


async def test_cancelling_serve_leaves_no_process_profile_or_task(private_tempdir):  # noqa: F811
    before = asyncio.all_tasks()
    mux = Multiplexer(2, warm=1, geoip=False)
    task = asyncio.ensure_future(mux.serve("127.0.0.1", 0))
    await _wait_until(lambda: mux.url is not None, 30)
    ws = await _client(mux).__aenter__()
    try:
        await _cdp(ws, 1, "Target.createTarget", {"url": "about:blank"})
        assert await _wait_until(lambda: len(_pids(mux)) == 2, 30)  # one busy, one warm
        processes = set()
        for pid in _pids(mux):
            processes |= {pid} | _descendants(pid)
        assert _profiles(private_tempdir)

        task.cancel()
        code, _ = await _closed(ws)
        await asyncio.wait([task])
        assert code == 1001
    finally:
        await ws.close()
    assert task.cancelled()
    assert await _wait_until(lambda: not [p for p in processes if _alive(p)], 10)
    assert not _profiles(private_tempdir)
    left = {t for t in asyncio.all_tasks() - before if t is not asyncio.current_task()}
    assert not left, left
    assert mux.url is None


# --------------------------------------------------------------------------- #
# Access
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("upgrade", [False, True], ids=["http", "upgrade"])
async def test_access_is_refused_before_anything_starts(upgrade):
    async with serving() as mux:
        port, token = _port(mux), mux.token
        host = ("Host", f"127.0.0.1:{port}")
        bearer = ("Authorization", f"Bearer {token}")
        path = "/devtools/browser/x" if upgrade else "/json/version"
        cases = [
            ([host], path, 401),
            ([host, ("Authorization", "Bearer " + "x" * 43)], path, 401),
            ([host, bearer], f"{path}?token={token}", 400),
            ([host, bearer], f"{path}?access_token=abc", 400),
            ([host, bearer], f"/devtools/browser/{token}", 400),
            ([host, bearer], f"/devtools/browser/{quote(quote(token, safe=''), safe='')}", 400),
            ([host, bearer, ("Origin", "http://127.0.0.1")], path, 403),
            ([("Host", f"evil.example:{port}"), bearer], path, 403),
            ([host, bearer, bearer], path, 400),
            ([host, bearer, ("Upgrade", "websocket"), ("Upgrade", "h2c")], path, 400),
        ]
        for headers, target, expected in cases:
            status, found, _ = await _http(port, target, headers, upgrade=upgrade)
            assert status == expected, (headers, target, status)
            if expected == 401:
                assert found.get("www-authenticate") == "Bearer"
        assert mux.status()["connections"] == 0
        assert all(s["launches"] == 0 for s in mux.status()["slots"])


@pytest.mark.parametrize(
    "request_head, body",
    [
        ("POST /json/version HTTP/1.1", [("Content-Length", "5")]),
        ("GET /devtools/browser/x HTTP/1.1", [("Content-Length", "5")]),
        ("POST /json/version HTTP/1.1", [("Transfer-Encoding", "chunked")]),
    ],
    ids=["post-length", "get-length", "chunked"],
)
async def test_a_request_with_a_body_gets_a_400(request_head, body):
    """E5: websockets reads no request body; such a request is answered 400
    (it used to be closed without a word), before any check or launch."""
    async with serving() as mux:
        reader, writer = await asyncio.open_connection("127.0.0.1", _port(mux))
        try:
            head = [request_head, *(f"{k}: {v}" for k, v in [*_good(mux), *body])]
            writer.write(("\r\n".join(head) + "\r\n\r\nhello").encode())
            status = await asyncio.wait_for(reader.readline(), 10)
            assert status.split()[1] == b"400", status
            rest = await asyncio.wait_for(reader.read(), 10)
            assert b"body" in rest
        finally:
            writer.close()
        assert mux.status()["connections"] == 0
        assert all(s["launches"] == 0 for s in mux.status()["slots"])


async def test_a_handshake_that_fails_after_the_place_was_taken_gives_it_back():
    async with serving() as mux:
        broken = [*_good(mux), ("Upgrade", "websocket"), ("Connection", "Upgrade")]
        status, _, _ = await _http(_port(mux), "/devtools/browser/x", broken)  # no key
        assert status == 400
        assert await _wait_until(lambda: mux.status()["clients"] == 0, 15)
        pids = [s["pid"] for s in mux.status()["slots"]]
        assert pids == [None]
        async with _client(mux) as ws:
            assert (await _cdp(ws, 1, "Browser.getVersion"))["result"]


@pytest.mark.parametrize("password", ["S3cretPW", "S3cret/PW", "S3/c@r:e#t?PW"])
async def test_a_chrome_that_will_not_start_is_retried_and_reported_without_secrets(
    tmp_path, monkeypatch, password
):
    monkeypatch.setattr(pool_module, "LAUNCH_WAIT", 3.0)
    fake = tmp_path / "chrome"
    fake.write_text('#!/bin/sh\necho "no display for you: $*" >&2\nexit 3\n')
    fake.chmod(0o755)
    proxies = [f"http://alice:{password}@127.0.0.1:18083"]
    async with serving(1, executable=str(fake), proxies=proxies) as mux:
        loop = asyncio.get_running_loop()
        start = loop.time()
        with pytest.raises(InvalidStatus) as refused:
            async with _client(mux):
                pass
        assert refused.value.response.status_code == 503
        assert 2.5 < loop.time() - start < 20
        body = refused.value.response.body.decode()
        assert "Chrome exited during launch" in body and "PW" not in body
        slot = mux.status()["slots"][0]
        assert slot["launch_failures"] >= 2  # retried, with a pause in between
        assert "exit code 3" in slot["error"]
        assert mux.status()["launch_failures"] == slot["launch_failures"]
        assert "PW" not in json.dumps(mux.status())
        # No retry once nobody wants the place; and the place is not lost.
        failures = slot["launch_failures"]
        await asyncio.sleep(1.5)
        assert mux.status()["slots"][0]["launch_failures"] == failures
        mux._pool.launch["executable"] = await find_chrome()
        async with _client(mux) as ws:
            assert (await _cdp(ws, 1, "Browser.getVersion"))["result"]
            assert mux.status()["slots"][0]["error"] is None


async def test_a_bad_proxy_url_never_shows_its_password(monkeypatch):
    monkeypatch.setattr(pool_module, "LAUNCH_WAIT", 2.0)
    async with serving(1, proxies=["htp://alice:S3cretPW@127.0.0.1:18084"]) as mux:
        with pytest.raises(InvalidStatus) as refused:
            async with _client(mux):
                pass
        body = refused.value.response.body.decode()
        assert refused.value.response.status_code == 503 and "scheme" in body
        assert "S3cretPW" not in body and "alice" not in body
        assert "S3cretPW" not in json.dumps(mux.status())


async def test_clients_that_hang_up_in_the_queue_leave_it_at_once():
    async with serving(1) as mux:
        port = _port(mux)
        async with _client(mux):
            ghosts = []
            for _ in range(3):
                _, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(_request("/devtools/browser/x", _good(mux), upgrade=True))
                ghosts.append(writer)
            assert await _wait_until(lambda: mux.status()["queue"] == 3, 5)
            for writer in ghosts:
                writer.close()
            assert await _wait_until(lambda: mux.status()["queue"] == 0, 5)
            real = asyncio.ensure_future(_client(mux).__aenter__())
            assert await _wait_until(lambda: mux.status()["queue"] == 1, 5)
        ws = await asyncio.wait_for(real, 30)
        try:
            assert (await _cdp(ws, 1, "Browser.getVersion"))["result"]
        finally:
            await ws.close()
        status = mux.status()
        assert status["connections"] == 2
        assert status["slots"][0]["launches"] == 2  # none for the ghosts


async def test_a_client_that_hangs_up_during_its_launch_leaves_the_chrome_to_the_next():
    """The launch a client was waiting for is not thrown away when it hangs
    up: the next client in the queue gets that Chrome (one launch, one
    proxy), with no close and relaunch in between."""
    async with serving(1, acquire_timeout=60) as mux:
        port = _port(mux)
        _, ghost = await asyncio.open_connection("127.0.0.1", port)
        ghost.write(_request("/devtools/browser/x", _good(mux), upgrade=True))
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "launching", 10)
        real = asyncio.ensure_future(_client(mux).__aenter__())
        assert await _wait_until(lambda: mux.status()["queue"] == 1, 5)
        ghost.close()
        ws = await asyncio.wait_for(real, 60)
        try:
            assert (await _cdp(ws, 1, "Browser.getVersion"))["result"]
            status = mux.status()
            assert status["slots"][0]["launches"] == 1, json.dumps(status)
        finally:
            await ws.close()


async def test_a_launch_nobody_wants_any_more_is_closed():
    """The client hangs up during its launch and nobody waits: the Chrome,
    once up, is closed (no warm Chrome was asked for) and the place is idle."""
    async with serving(1) as mux:
        _, ghost = await asyncio.open_connection("127.0.0.1", _port(mux))
        ghost.write(_request("/devtools/browser/x", _good(mux), upgrade=True))
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "launching", 10)
        ghost.close()
        assert await _wait_until(lambda: mux.status()["clients"] == 0, 5)
        assert await _wait_until(
            lambda: (
                mux.status()["slots"][0]["launches"] == 1
                and mux.status()["slots"][0]["state"] == "idle"
            ),
            60,
        ), json.dumps(mux.status())
        assert _pids(mux) == []


async def test_silent_sockets_are_dropped_and_do_not_crowd_out_a_client(monkeypatch):
    monkeypatch.setattr(server_module, "MAX_UNCHECKED", 8)
    monkeypatch.setattr(server_module, "REQUEST_TIMEOUT", 1.0)
    async with serving() as mux:
        mute = [await asyncio.open_connection("127.0.0.1", _port(mux)) for _ in range(40)]
        try:
            async with _client(mux) as ws:
                assert (await _cdp(ws, 1, "Browser.getVersion"))["result"]

            async def dropped(reader) -> bool:
                return await asyncio.wait_for(reader.read(), 5) == b""

            assert all(await asyncio.gather(*(dropped(r) for r, _ in mute)))
        finally:
            for _, writer in mute:
                writer.close()


async def test_waiting_clients_are_served_first_come_first_served():
    async with serving(1, acquire_timeout=60) as mux:
        order: list[int] = []
        first = await _client(mux).__aenter__()
        waiting = []

        async def wait(n: int):
            ws = await _client(mux).__aenter__()
            order.append(n)
            return ws

        for n in range(3):
            waiting.append(asyncio.ensure_future(wait(n)))
            assert await _wait_until(lambda n=n: mux.status()["queue"] == n + 1, 5)
        current = first
        for n in range(3):
            await current.close()
            current = await asyncio.wait_for(waiting[n], 30)
            assert order == list(range(n + 1))
        await current.close()


async def test_a_warm_chrome_takes_the_client_at_once_and_is_replaced():
    async with serving(1, warm=1) as mux:
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "ready", 30)
        (warm_pid,) = _pids(mux)
        loop = asyncio.get_running_loop()
        start = loop.time()
        async with _client(mux) as ws:
            assert loop.time() - start < 0.5
            assert _pids(mux) == [warm_pid] and mux.status()["slots"][0]["launches"] == 1
            assert (await _cdp(ws, 1, "Browser.getVersion"))["result"]
        ready = await _wait_until(lambda: mux.status()["slots"][0]["state"] == "ready", 30)
        assert ready, json.dumps(mux.status())
        assert _pids(mux) != [warm_pid]
        await asyncio.sleep(1)  # and it stays: no launch loop
        assert mux.status()["slots"][0]["launches"] == 2


async def test_a_burst_of_events_slows_a_slow_client_down_without_closing_it(monkeypatch):
    """100k console.log with Runtime.enable to a client that reads slowly: the relay
    holds the pipe up (bounded memory), health does not mistake that for a hang."""
    from tellurium.multiplexer import relay as relay_module

    monkeypatch.setattr(relay_module, "HIGH_WATER", 256 * 1024)
    monkeypatch.setattr(health, "INTERVAL", 0.2)
    monkeypatch.setattr(health, "TIMEOUT", 2.0)  # a reply may sit behind a burst
    total = 100_000
    async with serving() as mux, _client(mux) as ws:
        created = await _cdp(ws, 1, "Target.createTarget", {"url": "about:blank"})
        attached = await _cdp(
            ws,
            2,
            "Target.attachToTarget",
            {"targetId": created["result"]["targetId"], "flatten": True},
        )
        session = attached["result"]["sessionId"]
        await _cdp(ws, 3, "Runtime.enable", session=session)
        expression = f"for (let i = 0; i < {total}; i++) console.log(i)"
        await ws.send(
            json.dumps(
                {
                    "id": 4,
                    "method": "Runtime.evaluate",
                    "params": {"expression": expression},
                    "sessionId": session,
                }
            )
        )
        relay = mux._pool.places[0].relay
        peak, logs = 0, 0
        loop = asyncio.get_running_loop()
        start = loop.time()
        while logs < total:
            message = json.loads(await asyncio.wait_for(ws.recv(), 30))
            if message.get("method") == "Runtime.consoleAPICalled":
                assert message["params"]["args"][0]["value"] == logs
                logs += 1
                if logs % 50 == 0:
                    await asyncio.sleep(0.002)  # a slow client, but a live one
                    if relay._client is not None:
                        peak = max(peak, relay._client.queued)
        assert relay.pauses > 0  # the pipe was held up at least once
        assert peak <= 256 * 1024 + 64 * 1024
        assert (await _cdp(ws, 5, "Browser.getVersion"))["result"]
        status = mux.status()
        assert status["hangs"] == 0 and status["crashes"] == 0
        assert loop.time() - start < 120


@pytest.mark.parametrize("action", ["restart", "kill", "stall", "cancel"])
async def test_a_client_that_reads_nothing_cannot_hold_a_close_up(monkeypatch, action):
    """Chrome floods a client that stopped reading (tiny receive buffer): restarting
    or losing its Chrome, the stall limit and the server's shutdown all end in
    bounded time, cutting its socket, and free the place."""
    import socket

    from tellurium.multiplexer import relay as relay_module

    monkeypatch.setattr(relay_module, "HIGH_WATER", 1 << 20)
    monkeypatch.setattr(relay_module, "CLOSE_WAIT", 1.0)
    monkeypatch.setattr(relay_module, "STALL_LIMIT", 2.0 if action == "stall" else 600.0)
    mux = Multiplexer(1, geoip=False)
    task = asyncio.ensure_future(mux.serve("127.0.0.1", 0))
    await _wait_until(lambda: mux.url is not None, 30)
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    sock.connect(("127.0.0.1", _port(mux)))
    sock.setblocking(False)
    ws = await connect(
        f"ws://127.0.0.1:{_port(mux)}/devtools/browser/x",
        additional_headers={"Authorization": f"Bearer {mux.token}"},
        sock=sock,
        max_queue=1,
        max_size=None,
        open_timeout=60,
    )
    try:
        created = await _cdp(ws, 1, "Target.createTarget", {"url": "about:blank"})
        target = created["result"]["targetId"]
        attached = await _cdp(ws, 2, "Target.attachToTarget", {"targetId": target, "flatten": True})
        session = attached["result"]["sessionId"]
        await _cdp(ws, 3, "Runtime.enable", session=session)
        flood = 'for (let i = 0; i < 300; i++) console.log("x".repeat(100000))'
        params = {"expression": flood}
        await ws.send(
            json.dumps(
                {"id": 4, "method": "Runtime.evaluate", "params": params, "sessionId": session}
            )
        )
        # From here on the client reads nothing.
        relay = mux._pool.places[0].relay
        assert await _wait_until(lambda: relay.paused, 30)
        (pid,) = _pids(mux)
        loop = asyncio.get_running_loop()
        start = loop.time()
        if action == "restart":
            assert mux.restart(0)
        elif action == "kill":
            os.kill(pid, signal.SIGKILL)
        elif action == "cancel":
            task.cancel()
            await asyncio.wait_for(asyncio.wait([task]), 30)
            assert loop.time() - start < 20
            assert await _wait_until(lambda: not _alive(pid), 10)
            return
        freed = await _wait_until(
            lambda: mux.status()["clients"] == 0 and mux.status()["slots"][0]["state"] == "idle",
            25,
        )
        assert freed, json.dumps(mux.status())
        assert loop.time() - start < 20
        assert await _wait_until(lambda: not _alive(pid), 10)
        async with _client(mux) as other:
            assert (await _cdp(other, 1, "Browser.getVersion"))["result"]
    finally:
        ws.transport.abort()
        task.cancel()
        await asyncio.wait([task])


async def test_a_client_pausing_just_short_of_the_stall_does_not_get_chrome_killed(monkeypatch):
    """Production timings scaled down (probe every 1 s, 1 s timeout, two misses,
    stall at 6 s): a page that logs without pause, a client that stops reading for
    5 s and then reads fast. Chrome talks all along: no 1011. A Chrome in SIGSTOP
    is still caught."""
    from tellurium.multiplexer import relay as relay_module

    monkeypatch.setattr(health, "INTERVAL", 1.0)
    monkeypatch.setattr(health, "TIMEOUT", 1.0)
    monkeypatch.setattr(relay_module, "STALL_LIMIT", 6.0)
    monkeypatch.setattr(relay_module, "HIGH_WATER", 64 * 1024)
    async with serving() as mux:
        async with connect(
            f"ws://127.0.0.1:{_port(mux)}/devtools/browser/x",
            additional_headers={"Authorization": f"Bearer {mux.token}"},
            max_queue=1,  # not reading stops the socket at once; reading is fast
            max_size=None,
        ) as ws:
            created = await _cdp(ws, 1, "Target.createTarget", {"url": "about:blank"})
            target = created["result"]["targetId"]
            attached = await _cdp(
                ws, 2, "Target.attachToTarget", {"targetId": target, "flatten": True}
            )
            session = attached["result"]["sessionId"]
            await _cdp(ws, 3, "Runtime.enable", session=session)
            chatter = 'setInterval(() => console.log("x".repeat(200000)), 1)'
            await _cdp(ws, 4, "Runtime.evaluate", {"expression": chatter}, session=session)
            relay = mux._pool.places[0].relay
            loop = asyncio.get_running_loop()

            async def read_for(seconds: float) -> int:
                count, end = 0, loop.time() + seconds
                while loop.time() < end:
                    await asyncio.wait_for(ws.recv(), 10)
                    count += 1
                return count

            assert await read_for(1.0) > 0
            await asyncio.sleep(5.0)  # just short of the stall limit
            assert relay.pauses > 0
            assert await read_for(6.0) > 0
            status = mux.status()
            assert status["hangs"] == 0 and status["crashes"] == 0, status
            (pid,) = _pids(mux)

            os.kill(pid, signal.SIGSTOP)  # now a real hang
            try:
                code, reason = await _closed(ws, 20)
            finally:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGCONT)
            assert code == 1011 and "health probes" in reason
            assert mux.status()["hangs"] == 1


# --------------------------------------------------------------------------- #
# Authenticated proxy: the relay's own session (S1-B)
# --------------------------------------------------------------------------- #


def _own_sessions(mux: Multiplexer) -> set[str]:
    return {s for p in mux._pool.places if p.relay is not None for s in p.relay.own._handlers}


def _proxy_auth_tasks() -> list[asyncio.Task]:
    return [t for t in asyncio.all_tasks() if "ProxyAuth" in repr(t.get_coro())]


def _sessions_named(message: dict) -> set[str]:
    params = message.get("params") or {}
    return {s for s in (message.get("sessionId"), params.get("sessionId")) if s}


async def test_the_relay_answers_the_proxy_and_its_session_never_reaches_the_client(
    tls_context,  # noqa: F811
):
    async with FakeProxy(tunnels=True, tls=tls_context) as proxy:
        url = f"http://{USER}:{PASSWORD}@127.0.0.1:{proxy.port}"
        options = {"proxies": [url], "args": ["--ignore-certificate-errors"]}
        async with serving(1, warm=1, **options) as mux:
            # A warm Chrome answers the proxy before any client takes it.
            assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "ready", 60)
            (place,) = mux._pool.places
            assert place.chrome._proc.proxy_auth is not None
            (own,) = _own_sessions(mux)
            seen: list[dict] = []
            async with _client(mux) as ws:

                async def until(method: str, session: str = "") -> dict:
                    while True:
                        message = json.loads(await ws.recv())
                        seen.append(message)
                        if message.get("method") == method and (
                            not session or message.get("sessionId") == session
                        ):
                            return message

                await ws.send(json.dumps({"id": 1, "method": "Target.setDiscoverTargets",
                                          "params": {"discover": True}}))  # fmt: skip
                await ws.send(json.dumps({"id": 2, "method": "Target.setAutoAttach", "params": {
                    "autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True}}))  # fmt: skip
                await ws.send(json.dumps({"id": 3, "method": "Target.createTarget",
                                          "params": {"url": "about:blank"}}))  # fmt: skip
                target = (await asyncio.wait_for(until_reply(ws, 3, seen), 20))["result"]
                await ws.send(json.dumps({"id": 9, "method": "Target.attachToTarget",
                                          "params": {**target, "flatten": True}}))  # fmt: skip
                page = (await asyncio.wait_for(until_reply(ws, 9, seen), 20))["result"]
                page = page["sessionId"]
                for n, method in enumerate(("Page.enable", "Network.enable"), 4):
                    await ws.send(json.dumps({"id": n, "method": method, "sessionId": page}))
                for n, target in enumerate(("http://site.test/", "https://secure.test/"), 6):
                    await ws.send(json.dumps({"id": n, "method": "Page.navigate",
                                              "params": {"url": target}, "sessionId": page}))  # fmt: skip
                    await asyncio.wait_for(until("Page.loadEventFired", page), 20)
                await ws.send(json.dumps({"id": 8, "method": "Runtime.evaluate",
                                          "params": {"expression": "document.title"},
                                          "sessionId": page}))  # fmt: skip
                title = await asyncio.wait_for(until_reply(ws, 8, seen), 20)
                assert title["result"]["result"]["value"] == "proxied"
            assert ("GET http://site.test/ HTTP/1.1", GOOD_AUTH) in proxy.requests
            assert ("CONNECT secure.test:443 HTTP/1.1", GOOD_AUTH) in proxy.requests
            assert "GET https://secure.test/ (tunnel)" in proxy.lines()
            assert not [m for m in seen if own in _sessions_named(m)]
            assert not [m for m in seen if str(m.get("method", "")).startswith("Fetch.")]
            assert own not in json.dumps(seen)
            # The Chrome the client left is gone, with its answer to the proxy.
            assert await _wait_until(lambda: own not in _own_sessions(mux), 30)
        assert not _proxy_auth_tasks()


async def until_reply(ws, id: int, seen: list[dict]) -> dict:
    while True:
        message = json.loads(await ws.recv())
        seen.append(message)
        if message.get("id") == id:
            return message


async def test_a_lost_chrome_takes_its_answer_to_the_proxy_with_it():
    async with FakeProxy() as proxy:
        url = f"http://{USER}:{PASSWORD}@127.0.0.1:{proxy.port}"
        async with serving(1, proxies=[url]) as mux:
            async with _client(mux) as ws:
                await _cdp(ws, 1, "Browser.getVersion")
                (place,) = mux._pool.places
                auth = place.chrome._proc.proxy_auth
                assert auth is not None and _own_sessions(mux)
                os.kill(place.chrome.pid, signal.SIGKILL)
                code, _ = await _closed(ws)
                assert code == 1011
            # The client is told first; then the Chrome is closed, with its answer.
            assert await _wait_until(lambda: not auth._active and not auth._tasks, 30)
            async with _client(mux) as ws:  # the new Chrome answers again
                created = await _cdp(ws, 1, "Target.createTarget", {"url": "http://site.test/"})
                assert created["result"]["targetId"]
                assert await _wait_until(lambda: proxy.requests, 20)
                assert proxy.requests[0] == ("GET http://site.test/ HTTP/1.1", GOOD_AUTH)
        assert not _proxy_auth_tasks()


async def test_the_client_cannot_detach_the_own_session():
    """Every way a client has to detach a session, tried on the relay's own:
    refused, or harmless; Chrome still answers the proxy afterwards."""
    async with FakeProxy() as proxy:
        url = f"http://{USER}:{PASSWORD}@127.0.0.1:{proxy.port}"
        async with serving(1, proxies=[url]) as mux, _client(mux) as ws:
            (place,) = mux._pool.places
            (own,) = _own_sessions(mux)
            (own_target,) = place.relay.own._targets
            root = (await _cdp(ws, 1, "Target.getTargetInfo"))["result"]["targetInfo"]
            assert root["type"] == "browser" and root["targetId"] != own_target
            tries = [
                {"sessionId": own},
                {"targetId": own_target},
                {"targetId": root["targetId"]},  # the root's own: Chrome has no session for it
                {},  # Chrome: "Session id must be specified"
            ]
            for n, params in enumerate(tries, 2):
                reply = await _cdp(ws, n, "Target.detachFromTarget", params)
                assert "error" in reply, (params, reply)
            refused = await _cdp(ws, 7, "Fetch.disable", session=own)
            assert refused["error"]["code"] == -32001
            for n, flag in enumerate((True, False), 8):
                await _cdp(ws, n, "Target.setAutoAttach",
                           {"autoAttach": flag, "waitForDebuggerOnStart": False, "flatten": True})  # fmt: skip
            assert await place.relay.call("Browser.getVersion", timeout=10, session_id=own)
            await _cdp(ws, 10, "Target.createTarget", {"url": "http://site.test/"})
            assert await _wait_until(lambda: proxy.requests, 20)
            assert proxy.requests[0] == ("GET http://site.test/ HTTP/1.1", GOOD_AUTH)


async def test_chrome_detaches_a_browser_session_by_its_target_id():
    """Why the relay refuses ``Target.detachFromTarget`` with its own session's
    target id: Chrome (observed on 156) detaches that browser session by
    target id too. On a bare pipe, no relay: if Chrome stops doing so, this
    test says the refusal by target id may go."""
    async with RawChrome.launch(headless=True, geoip=False) as raw:
        relay = Relay(raw.transport)
        relay.start()
        try:
            attached = await relay.call("Target.attachToBrowserTarget", timeout=10)
            session = attached["sessionId"]
            info = await relay.call("Target.getTargetInfo", timeout=10, session_id=session)
            target = info["targetInfo"]["targetId"]
            await relay.call("Target.detachFromTarget", {"targetId": target}, timeout=10)
            with pytest.raises(CommandError, match="Session with given id not found"):
                await relay.call("Browser.getVersion", timeout=10, session_id=session)
        finally:
            await relay.close()

"""Administration of the multiplexer (``/admin/status``, ``/admin/slots/<id>/restart``)
behind the same checks as CDP, and ``tellurium multiplex`` run as a process:
its proxies file, its messages, and Ctrl-C or SIGTERM leaving nothing behind."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import signal
import socket
import sys
from pathlib import Path

import pytest

pytest.importorskip("websockets")

from websockets.asyncio.client import connect  # noqa: E402

from tellurium.browser.raw_chrome import RawChrome  # noqa: E402
from tellurium.multiplexer import command  # noqa: E402
from tests.console_signals import NEW_GROUP, interrupt  # noqa: E402
from tests.integration.test_multiplexer import (  # noqa: E402, F401 - autouse fixtures
    _cdp,
    _client,
    _closed,
    _good,
    _port,
    serving,
    token_file,
)
from tests.integration.test_raw_chrome import (  # noqa: E402, F401 - autouse fixture
    _alive,
    _descendants,
    _profiles,
    _wait_until,
    private_tempdir,
)
from tests.platform_marks import needs_proc  # noqa: E402


async def _call(
    port: int,
    method: str,
    target: str,
    headers: list[tuple[str, str]],
) -> tuple[int, dict, bytes]:
    """A raw HTTP/1.1 request with an empty body: status, headers, body."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        lines = [f"{method} {target} HTTP/1.1", *(f"{k}: {v}" for k, v in headers)]
        if method != "GET":
            lines.append("Content-Length: 0")
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
        status = await asyncio.wait_for(reader.readline(), 30)
        found = {}
        while (line := await reader.readline()) not in (b"\r\n", b""):
            name, _, value = line.decode().partition(":")
            found[name.strip().lower()] = value.strip()
        body = await reader.readexactly(int(found.get("content-length", "0")))
        return int(status.split()[1]), found, body
    finally:
        writer.close()


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #


@needs_proc
async def test_status_lists_places_and_totals_without_any_secret():
    proxies = ["http://127.0.0.1:18091", "http://user:S3cretPW@127.0.0.1:18092"]
    async with serving(2, proxies=proxies, warm=2) as mux:
        port = _port(mux)
        assert await _wait_until(lambda: all(s["pid"] for s in mux.status()["slots"]), 60)
        status, headers, body = await _call(port, "GET", "/admin/status", _good(mux))
        assert status == 200 and headers["content-type"].startswith("application/json")
        text = body.decode()
        assert "S3cretPW" not in text and "user" not in text and mux.token not in text
        found = json.loads(text)
        for key in ("size", "warm", "clients", "queue", "connections", "crashes", "hangs"):
            assert key in found
        assert found["size"] == 2 and found["warm"] == 2 and found["queue"] == 0
        slots = found["slots"]
        assert [s["id"] for s in slots] == [0, 1]
        for slot in slots:
            assert {"state", "pid", "proxy", "age", "restarts"} <= set(slot)
            assert slot["pid"] and _alive(slot["pid"])
        assert sorted(s["proxy"] for s in slots) == [
            "http://127.0.0.1:18091",
            "http://127.0.0.1:18092",
        ]


async def test_status_with_a_query_and_a_trailing_slash():
    async with serving() as mux:
        port = _port(mux)
        assert (await _call(port, "GET", "/admin/status/", _good(mux)))[0] == 200
        assert (await _call(port, "GET", "/admin/status?pretty=1", _good(mux)))[0] == 200


# --------------------------------------------------------------------------- #
# Restart
# --------------------------------------------------------------------------- #


@needs_proc
async def test_restart_replaces_the_chrome_and_closes_its_client_with_1012():
    async with serving(2) as mux:
        port = _port(mux)
        async with _client(mux) as ws:
            await _cdp(ws, 1, "Browser.getVersion")
            (slot,) = [s for s in mux.status()["slots"] if s["state"] == "busy"]
            status, _, _ = await _call(
                port, "POST", f"/admin/slots/{slot['id']}/restart", _good(mux)
            )
            assert status == 202
            code, reason = await _closed(ws)
            assert code == 1012 and reason
        assert await _wait_until(lambda: not _alive(slot["pid"]), 30)
        after = mux.status()["slots"][slot["id"]]
        assert after["restarts"] == 1
        assert mux.status()["crashes"] == 0


async def test_restart_of_a_place_without_chrome_is_409():
    async with serving(1) as mux:
        status, _, body = await _call(_port(mux), "POST", "/admin/slots/0/restart", _good(mux))
        assert status == 409 and b"no Chrome" in body
        assert mux.status()["slots"][0]["launches"] == 0


@needs_proc
async def test_restart_while_launching_is_409_then_a_warm_chrome_is_replaced(monkeypatch):
    launch, go = RawChrome.launch, asyncio.Event()

    async def held(**options):
        await go.wait()
        return await launch(**options)

    monkeypatch.setattr(RawChrome, "launch", held)
    async with serving(1, warm=1) as mux:
        port = _port(mux)
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "launching", 30)
        status, _, _ = await _call(port, "POST", "/admin/slots/0/restart", _good(mux))
        assert status == 409
        go.set()
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "ready", 60)
        warm = mux.status()["slots"][0]
        assert warm["restarts"] == 0 and warm["launches"] == 1
        status, _, body = await _call(port, "POST", "/admin/slots/0/restart", _good(mux))
        assert status == 202 and json.loads(body) == {"id": 0, "restarting": True}
        assert await _wait_until(lambda: not _alive(warm["pid"]), 30)
        assert await _wait_until(lambda: mux.status()["slots"][0]["state"] == "ready", 60)
        after = mux.status()["slots"][0]
        assert after["pid"] != warm["pid"] and after["restarts"] == 1 and after["launches"] == 2
        assert mux.status()["crashes"] == 0


@pytest.mark.parametrize(
    "target",
    [
        "/admin/slots/7/restart",
        "/admin/slots/x/restart",
        "/admin/slots/-1/restart",
        "/admin/slots/0/stop",
        "/admin/nothing",
        "/admin/slots/%30/restart",
    ],
)
async def test_unknown_admin_routes_are_404(target):
    async with serving(2) as mux:
        status, _, _ = await _call(_port(mux), "POST", target, _good(mux))
        assert status == 404, target


@pytest.mark.parametrize(
    "method, target, allow",
    [
        ("GET", "/admin/slots/0/restart", "POST"),
        ("PUT", "/admin/slots/0/restart", "POST"),
        ("DELETE", "/admin/slots/0/restart", "POST"),
        ("POST", "/admin/status", "GET"),
        ("PUT", "/admin/status", "GET"),
        ("POST", "/json/version", "GET"),
        ("POST", "/devtools/browser/x", "GET"),
    ],
)
async def test_other_methods_are_405_with_allow(method, target, allow):
    async with serving() as mux:
        status, headers, _ = await _call(_port(mux), method, target, _good(mux))
        assert status == 405 and headers["allow"] == allow
        assert mux.status()["slots"][0]["launches"] == 0


async def test_a_request_body_is_refused():
    """websockets reads no body: it drops the connection (or answers 400) unheard."""
    async with serving(1, warm=1) as mux:
        assert await _wait_until(lambda: mux.status()["slots"][0]["pid"], 60)
        reader, writer = await asyncio.open_connection("127.0.0.1", _port(mux))
        try:
            lines = [
                "POST /admin/slots/0/restart HTTP/1.1",
                *(f"{k}: {v}" for k, v in _good(mux)),
                "Content-Length: 2",
            ]
            writer.write(("\r\n".join(lines) + "\r\n\r\n{}").encode())
            status = await asyncio.wait_for(reader.readline(), 30)
            assert status == b"" or int(status.split()[1]) == 400
        finally:
            writer.close()
        await asyncio.sleep(0.5)
        assert mux.status()["slots"][0]["restarts"] == 0


# --------------------------------------------------------------------------- #
# Access
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "method, path", [("GET", "/admin/status"), ("POST", "/admin/slots/0/restart")]
)
async def test_admin_routes_refuse_like_cdp_before_doing_anything(method, path):
    async with serving(1, warm=1) as mux:
        port, token = _port(mux), mux.token
        assert await _wait_until(lambda: mux.status()["slots"][0]["pid"], 60)
        pid = mux.status()["slots"][0]["pid"]
        host = ("Host", f"127.0.0.1:{port}")
        bearer = ("Authorization", f"Bearer {token}")
        cases = [
            ([host], path, 401),
            ([host, ("Authorization", "Bearer " + "x" * 43)], path, 401),
            ([host, ("Authorization", f"Basic {token}")], path, 401),
            ([host, bearer], f"{path}?token={token}", 400),
            ([host, bearer], f"/admin/slots/{token}/restart", 400),
            ([host, bearer, ("Origin", "http://127.0.0.1")], path, 403),
            ([host, bearer, ("Origin", "null")], path, 403),
            ([("Host", f"evil.example:{port}"), bearer], path, 403),
            ([host, bearer, bearer], path, 400),
        ]
        for headers, target, expected in cases:
            status, found, body = await _call(port, method, target, headers)
            assert status == expected, (headers, target, status)
            assert b"slots" not in body
            if expected == 401:
                assert found.get("www-authenticate") == "Bearer"
        assert mux.status()["slots"][0]["restarts"] == 0
        assert mux.status()["slots"][0]["pid"] == pid


# --------------------------------------------------------------------------- #
# Proxies file
# --------------------------------------------------------------------------- #


def test_proxies_file_skips_blank_lines_and_comments(tmp_path):
    path = tmp_path / "proxies.txt"
    path.write_text(
        "# exits\n\nhttp://127.0.0.1:8080\n   \n  socks5://u:p@127.0.0.1:1080  \n"
        "  # indented comment\nhttps://127.0.0.1:8443\n"
    )
    assert command.read_proxies(path) == [
        "http://127.0.0.1:8080",
        "socks5://u:p@127.0.0.1:1080",
        "https://127.0.0.1:8443",
    ]


@pytest.mark.parametrize(
    "line",
    [
        "127.0.0.1:8080:user:S3cretPW",
        "ftp://user:S3cretPW@127.0.0.1:21",
        "http://user:S3cretPW@",
        "http://user:S3cretPW@127.0.0.1:99999",
        "http://user:S3cretPW@127.0.0.1:8080 trailing",
        "http://u:S3cretPW@a\x00a",
        "http://user:S3cret\x01PW@127.0.0.1:8080",
        "http://us\x00er:S3cretPW@127.0.0.1:8080",
        "http://user:S3cretPW@127.0.0.1\x7f:8080",
        "socks5://user:S3cretPW@127.0.0.1\x1b[2J:1080",
    ],
)
def test_a_bad_proxy_line_names_its_number_but_never_its_text(tmp_path, line):
    path = tmp_path / "proxies.txt"
    path.write_text(f"# first\nhttp://127.0.0.1:8080\n\n{line}\n")
    with pytest.raises(command.ProxiesFileError) as error:
        command.read_proxies(path)
    message = str(error.value)
    assert "line 4" in message and str(path) in message
    assert "S3cretPW" not in message


def test_an_empty_or_missing_proxies_file_is_an_error(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("# nothing\n\n")
    with pytest.raises(command.ProxiesFileError, match="no proxy"):
        command.read_proxies(empty)
    with pytest.raises(command.ProxiesFileError, match="cannot read"):
        command.read_proxies(tmp_path / "missing.txt")


# --------------------------------------------------------------------------- #
# tellurium multiplex, as a process
# --------------------------------------------------------------------------- #

_CLI = "import sys; from tellurium.cli import main; sys.argv[0] = 'tellurium'; main()"


def _cli_env(tmp_path: Path) -> dict[str, str]:
    """A home of its own (token file), an empty patched cache, the managed stock
    Chromes of the real home (no download), no Wayland window."""
    home = tmp_path / "cli-home"
    (home / ".tellurium").mkdir(parents=True, exist_ok=True)
    managed = Path.home() / ".tellurium" / "browsers"
    if managed.is_dir() and not (home / ".tellurium" / "browsers").exists():
        (home / ".tellurium" / "browsers").symlink_to(managed)
    env = {**os.environ, "HOME": str(home), "TELLURIUM_CACHE_DIR": str(tmp_path / "cache")}
    env.pop("WAYLAND_DISPLAY", None)
    return env


async def _run_cli(tmp_path: Path, *args: str, prelude: str = "") -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import sys; " + prelude + _CLI,
        "multiplex",
        *args,
        env=_cli_env(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(proc.communicate(), 60)
    return proc.returncode, out.decode(), err.decode()


@pytest.mark.parametrize(
    "signum, group, again",
    [
        (signal.SIGINT, False, False),
        (signal.SIGTERM, False, False),
        # The terminal (or ssh) went away: its whole group. No SIGHUP on Windows,
        # where the test is skipped (needs_proc) but the module still collects.
        (getattr(signal, "SIGHUP", None), True, False),
        (signal.SIGINT, False, True),  # Ctrl-C pressed again and again while it closes
        (signal.SIGINT, True, True),
    ],
    ids=["SIGINT", "SIGTERM", "SIGHUP-group", "SIGINT-again", "SIGINT-group-again"],
)
@needs_proc
async def test_the_command_serves_then_a_signal_closes_everything(
    tmp_path,
    private_tempdir,  # noqa: F811
    signum,
    group,
    again,
):
    env = _cli_env(tmp_path)
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _CLI,
        "multiplex",
        "--pool",
        "2",
        "--warm",
        "1",
        "--browser",
        "stock",
        "--listen",
        "127.0.0.1:0",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,  # as setsid: a group of its own, Chromes included
    )
    try:
        first = (await asyncio.wait_for(proc.stdout.readline(), 90)).decode()
        url = re.search(r"http://127\.0\.0\.1:\d+", first)
        assert url, first
        port = int(url.group(0).rsplit(":", 1)[1])
        token_path = Path(env["HOME"]) / ".tellurium" / "multiplex-token"
        assert str(token_path) in (await proc.stdout.readline()).decode()
        token = token_path.read_text().strip()
        good = [("Host", f"127.0.0.1:{port}"), ("Authorization", f"Bearer {token}")]

        async def slots() -> list[dict]:
            status, _, body = await _call(port, "GET", "/admin/status", good)
            assert status == 200
            return json.loads(body)["slots"]

        deadline = asyncio.get_running_loop().time() + 60
        while not any(s["pid"] for s in await slots()):
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.1)
        async with connect(
            f"ws://127.0.0.1:{port}/devtools/browser/x",
            additional_headers={"Authorization": f"Bearer {token}"},
            open_timeout=60,
        ) as ws:
            await _cdp(ws, 1, "Browser.getVersion")
            # The client took the warm Chrome; a new warm one follows.
            deadline = asyncio.get_running_loop().time() + 60
            while len(pids := {s["pid"] for s in await slots() if s["pid"]}) < 2:
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.1)
            family = _descendants(proc.pid)
            assert pids <= family

            def send() -> None:
                with contextlib.suppress(ProcessLookupError):
                    if group:
                        os.killpg(proc.pid, signum)
                    else:
                        proc.send_signal(signum)

            send()
            # A signal every 0.05 s until it exits: one lands at every stage of the closing.
            repeat = asyncio.ensure_future(_every(0.05, send)) if again else None
            try:
                code, _ = await _closed(ws)
                # With the group signalled, Chrome may go first (1011) or be closed (1001).
                assert code == 1001 or (group and code == 1011)
                assert await asyncio.wait_for(proc.wait(), 60) == 0
            finally:
                if repeat is not None:
                    repeat.cancel()
        rest = (await proc.stdout.read()).decode() + (await proc.stderr.read()).decode()
        assert token not in first + rest
        assert await _wait_until(lambda: not any(_alive(p) for p in family), 15)
        assert _profiles(private_tempdir) == []
    finally:
        if proc.returncode is None:
            os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()


async def test_ctrl_c_closes_the_command_with_0_on_every_system(
    tmp_path,
    private_tempdir,  # noqa: F811
):
    """Ctrl-C, or on Windows Ctrl-Break to a console group of its own (a real
    console event, not ``TerminateProcess``): the client is told 1001, every
    Chrome and profile goes, and the exit code is 0."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _CLI,
        "multiplex",
        "--pool",
        "1",
        "--warm",
        "1",
        "--browser",
        "stock",
        "--listen",
        "127.0.0.1:0",
        env=_cli_env(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **NEW_GROUP,
    )
    try:
        first = (await asyncio.wait_for(proc.stdout.readline(), 90)).decode()
        url = re.search(r"http://127\.0\.0\.1:\d+", first)
        assert url, first + (await proc.stderr.read()).decode()
        port = int(url.group(0).rsplit(":", 1)[1])
        # Where the token is: HOME on POSIX, the user profile on Windows.
        second = (await proc.stdout.readline()).decode()
        token = Path(second.split("token in ", 1)[1].strip()).read_text().strip()
        try:
            ws = await connect(
                f"ws://127.0.0.1:{port}/devtools/browser/x",
                additional_headers={"Authorization": f"Bearer {token}"},
                open_timeout=60,
            )
        except TimeoutError:
            proc.kill()
            raise AssertionError((await proc.stderr.read()).decode()) from None
        async with ws:
            await _cdp(ws, 1, "Browser.getVersion")
            interrupt(proc)
            code, _ = await _closed(ws)
            assert code == 1001
        assert await asyncio.wait_for(proc.wait(), 60) == 0
        rest = (await proc.stdout.read()).decode()
        assert "stopped" in rest + (await proc.stderr.read()).decode()
        assert await _wait_until(lambda: _profiles(private_tempdir) == [], 15)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


async def _every(interval: float, action) -> None:
    while True:
        await asyncio.sleep(interval)
        action()


async def test_a_bad_proxies_file_stops_the_command_before_any_chrome(tmp_path):
    proxies = tmp_path / "proxies.txt"
    proxies.write_text("http://127.0.0.1:8080\n# ok\nhttp://user:S3cretPW@127.0.0.1:99999\n")
    code, out, err = await _run_cli(
        tmp_path, "--pool", "1", "--browser", "stock", "--proxies", str(proxies)
    )
    assert code == 2 and "line 3" in err and "S3cretPW" not in out + err


async def test_without_the_patched_chrome_the_command_says_what_to_do(tmp_path):
    code, _, err = await _run_cli(tmp_path, "--pool", "1")
    assert code == 2
    assert "tellurium download-browser --browser patched" in err and "--browser stock" in err


async def test_without_the_extra_the_command_says_what_to_install(tmp_path):
    code, _, err = await _run_cli(
        tmp_path, "--pool", "1", "--browser", "stock", prelude="sys.modules['websockets'] = None; "
    )
    assert code == 2 and "pip install 'tellurium[multiplex]'" in err


def test_the_warning_for_a_network_address_says_what_is_exposed():
    assert command.listen_warning("127.0.0.1") is None
    assert command.listen_warning("::1") is None
    named = command.listen_warning("192.0.2.7")
    assert "192.0.2.7" in named and "plain text" in named and "Host" not in named
    for wildcard in ("0.0.0.0", "::"):
        warning = command.listen_warning(wildcard)
        assert "plain text" in warning and "Host check is off" in warning


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="chmod does not make a folder unwritable on Windows (that takes an ACL)",
)
async def test_a_token_home_that_cannot_be_written_is_named_as_such(tmp_path):
    _cli_env(tmp_path)
    home = tmp_path / "cli-home" / ".tellurium"
    home.chmod(0o555)
    try:
        code, _, err = await _run_cli(
            tmp_path, "--pool", "1", "--browser", "stock", "--listen", "127.0.0.1:0"
        )
    finally:
        home.chmod(0o755)
    assert code == 2 and "token file" in err and "cannot listen" not in err


async def test_a_port_in_use_is_named_as_such(tmp_path):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        code, _, err = await _run_cli(
            tmp_path, "--pool", "1", "--browser", "stock", "--listen", f"127.0.0.1:{port}"
        )
    assert code == 2 and f"cannot listen on 127.0.0.1:{port}" in err and "token" not in err


@pytest.mark.parametrize(
    "args, message",
    [
        (["--pool", "0"], "--pool"),
        (["--pool", "2", "--warm", "3"], "--warm"),
        (["--pool", "1", "--acquire-timeout", "0"], "--acquire-timeout"),
        (["--pool", "1", "--listen", "localhost"], "--listen"),
    ],
)
async def test_bad_options_are_named(tmp_path, args, message):
    code, _, err = await _run_cli(tmp_path, *args, "--browser", "stock")
    assert code == 2 and message in err

"""Temporary probe (R3-C): where the time goes in reds 7 and 8 on the runners.

Red 7: the first navigation of a fresh browser to a page whose image never
comes; timings of the server (document asked) and of each CDP command.
Red 8: RawChrome.close() on a fresh Chrome; whether the grace ran out (our
TerminateProcess, exit code 1) or Chrome itself exited 1.
Each run prints one ``PROBE`` JSON line (run with ``-s``).
"""

from __future__ import annotations

import asyncio
import http.server
import json
import sys
import threading
import time

import pytest

from tellurium.browser.navigation import NavigationTimeoutError
from tellurium.browser.raw_chrome import RawChrome
from tests.private_temp import private_temp

RUNS = 5


@pytest.fixture(scope="module")
def probe_server():
    release = threading.Event()
    arrivals: list[tuple[str, float]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            arrivals.append((self.path, time.monotonic()))
            if self.path.startswith("/img"):
                release.wait(60)
                return
            body = b"<html><body><p>x</p><img src='/img'></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", arrivals
    release.set()
    httpd.shutdown()


@pytest.mark.parametrize("i", range(RUNS))
async def test_probe_load_phase(browser, probe_server, i):
    base, arrivals = probe_server
    tab = browser.main_tab
    session = tab._session
    original = session.send
    start = time.monotonic()
    commands: list[tuple[str, float, float]] = []

    async def timed(method, params=None, timeout=None):
        t0 = time.monotonic()
        try:
            return await original(method, params, timeout)
        finally:
            commands.append((method, round(t0 - start, 3), round(time.monotonic() - start, 3)))

    session.send = timed
    phase = "none"
    try:
        await asyncio.wait_for(tab.get(f"{base}/doc?{i}", wait_until="load", timeout=5), 20)
    except NavigationTimeoutError as exc:
        phase = exc.phase
    finally:
        session.send = original
    end = round(time.monotonic() - start, 3)
    seen = [(p, round(t - start, 3)) for p, t in arrivals if p.endswith(f"?{i}") or t >= start]
    print("PROBE7", json.dumps({"i": i, "phase": phase, "end": end, "cmds": commands, "srv": seen}))
    assert phase == "load"


@pytest.mark.parametrize("i", range(RUNS))
async def test_probe_close(monkeypatch, tmp_path_factory, tmp_path, i):
    tmp_path_factory.getbasetemp()
    log = tmp_path / "chrome.log"
    with private_temp(monkeypatch):
        t_launch = time.monotonic()
        raw = await RawChrome.launch(headless=True, chrome_log=log)
        launched = round(time.monotonic() - t_launch, 3)
        process = raw._proc.process
        signals: list[float] = []
        start = time.monotonic()
        real_terminate = process.terminate
        real_kill = process.kill

        def terminate():
            signals.append(round(time.monotonic() - start, 3))
            real_terminate()

        def kill():
            signals.append(round(time.monotonic() - start, 3))
            real_kill()

        process.terminate = terminate
        process.kill = kill
        exited: list[float] = []

        async def watch():
            while process.poll() is None:
                await asyncio.sleep(0.02)
            exited.append(round(time.monotonic() - start, 3))

        watcher = asyncio.ensure_future(watch())
        await asyncio.wait_for(raw.close(), 30)
        await asyncio.wait_for(watcher, 5)
        tail = ""
        if process.returncode != 0:
            try:
                tail = log.read_text(errors="replace")[-3000:]
            except OSError as exc:
                tail = repr(exc)
        record = {
            "i": i,
            "launch": launched,
            "code": process.returncode,
            "signals": signals,
            "exited": exited,
            "closed": round(time.monotonic() - start, 3),
            "log": tail,
        }
        print("PROBE8", json.dumps(record))
        assert process.returncode == 0


@pytest.mark.parametrize("i", range(5))
async def test_probe_second_navigation(browser, probe_server, i):
    """Is the ~1 s before the request reaches the server only the first one's?"""
    base, arrivals = probe_server
    tab = browser.main_tab
    times = []
    for n in range(2):
        start = time.monotonic()
        await asyncio.wait_for(tab.get(f"{base}/doc?s{i}n{n}", wait_until="commit"), 30)
        got = [t for p, t in arrivals if p == f"/doc?s{i}n{n}"]
        times.append((round(got[0] - start, 3), round(time.monotonic() - start, 3)))
    print("PROBE7B", json.dumps({"i": i, "first": times[0], "second": times[1]}))


@pytest.mark.skipif(sys.platform != "win32", reason="NtSuspendProcess")
@pytest.mark.parametrize("grace", [5.0, 15.0])
async def test_probe_close_with_a_stall(monkeypatch, tmp_path_factory, grace):
    """Chrome suspended 6 s right after Browser.close: past a 5 s grace the
    signals end it; what exit code does that give on Windows?"""
    import ctypes

    from tellurium.browser import raw_chrome

    tmp_path_factory.getbasetemp()
    monkeypatch.setattr(raw_chrome, "CLOSE_GRACE", grace)
    ntdll = ctypes.WinDLL("ntdll")
    with private_temp(monkeypatch):
        raw = await RawChrome.launch(headless=True)
        process = raw._proc.process
        handle = process._handle
        signals: list[float] = []
        start = time.monotonic()
        real_terminate = process.terminate

        def terminate():
            signals.append(round(time.monotonic() - start, 3))
            real_terminate()

        process.terminate = terminate
        process.kill = terminate
        send = raw.transport.send

        async def stalled(data):
            await send(data)
            ntdll.NtSuspendProcess(ctypes.c_void_p(handle))
            asyncio.get_running_loop().call_later(
                6, lambda: ntdll.NtResumeProcess(ctypes.c_void_p(handle))
            )

        raw.transport.send = stalled
        await asyncio.wait_for(raw.close(), 60)
        print(
            "PROBE8S",
            json.dumps({"grace": grace, "code": process.returncode, "signals": signals}),
        )

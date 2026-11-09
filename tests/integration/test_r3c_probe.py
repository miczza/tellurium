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
import threading
import time

import pytest

from tellurium.browser.navigation import NavigationTimeoutError
from tellurium.browser.raw_chrome import RawChrome
from tests.private_temp import private_temp

RUNS = 15


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

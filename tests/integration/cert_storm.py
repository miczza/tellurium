"""A forced reproduction of the mute Chrome of macOS (rosso noto 1 of R4):
certificate verifications in a loop.

Chrome went mute with its main thread and a ``ThreadPoolForegroundWorker``
both parked on the write lock of BoringSSL's certificate pool, each freeing a
``net::X509Certificate`` at the end of a TLS certificate verification (run
43001946271). At launch those verifications are Chrome's own background
fetches, a handful; here a page keeps many going at once: HTTPS fetches to
local servers under a fresh host name each time (``*.storm.test`` mapped to
127.0.0.1), so that no verification is served from Chrome's cache. A command
to the page every second is what the hang probe watches.

Not part of the suite (no ``test_`` prefix): run it by path, on the CI with
``-f tests=tests/integration/cert_storm.py``. ``$TELLURIUM_CERT_STORM_SECONDS``
sets the time in all (one Chrome per ``ROUND`` seconds).
"""

from __future__ import annotations

import asyncio
import http.server
import os
import ssl
import subprocess
import threading
import time
from pathlib import Path

import pytest

BUDGET = float(os.environ.get("TELLURIUM_CERT_STORM_SECONDS", "1200"))
ROUND = 20.0
SERVERS = 6
PARALLEL = 24
_started = time.monotonic()

_PAGE = """<!DOCTYPE html><title>cert storm</title><script>
window.done = 0; window.failed = 0;
const ports = %s;
async function one() {
  for (;;) {
    const host = 'h' + Math.random().toString(36).slice(2) + '.storm.test';
    const port = ports[Math.floor(Math.random() * ports.length)];
    try { await fetch(`https://${host}:${port}/`, {mode: 'no-cors', cache: 'no-store'}); done++; }
    catch (e) { failed++; }
  }
}
for (let i = 0; i < %d; i++) one();
</script>"""


class _Quick(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_GET(self):  # noqa: N802 (http.server's name)
        page = self.path == "/storm.html"
        body = _PAGE_BODY if page else b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/html" if page else "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass  # Chrome drops connections it no longer needs


_PAGE_BODY = b""


def _cert(folder: Path, i: int) -> tuple[Path, Path]:
    key, crt = folder / f"k{i}.pem", folder / f"c{i}.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
         "-keyout", str(key), "-out", str(crt), "-subj", f"/CN=storm{i}.test",
         "-addext", "subjectAltName=DNS:*.storm.test"],
        check=True, capture_output=True,
    )  # fmt: skip
    return key, crt


@pytest.fixture(scope="module")
def storm_servers(tmp_path_factory):
    global _PAGE_BODY
    folder = tmp_path_factory.mktemp("certs")
    servers, ports = [], []
    for i in range(SERVERS):
        key, crt = _cert(folder, i)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(crt, key)
        srv = _Server(("127.0.0.1", 0), _Quick)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        ports.append(srv.server_address[1])
    plain = _Server(("127.0.0.1", 0), _Quick)
    threading.Thread(target=plain.serve_forever, daemon=True).start()
    _PAGE_BODY = (_PAGE % (ports, PARALLEL)).encode()
    yield f"http://127.0.0.1:{plain.server_address[1]}/storm.html"
    for srv in [*servers, plain]:
        srv.shutdown()


@pytest.mark.parametrize("round_", range(int(BUDGET // ROUND) + 1))
async def test_chrome_answers_while_certificates_are_verified_in_a_loop(round_, storm_servers):
    from tellurium import Browser

    if time.monotonic() - _started > BUDGET:
        pytest.skip("the storm's time is spent")
    args = ["--ignore-certificate-errors", "--host-resolver-rules=MAP *.storm.test 127.0.0.1"]
    browser = await Browser.launch(headless=True, args=args)
    try:
        tab = await browser.new_tab(storm_servers)
        end = time.monotonic() + ROUND
        while time.monotonic() < end:
            await asyncio.sleep(1.0)
            done = await tab.eval("window.done")
        print(f"round {round_}: {done} fetches, {await tab.eval('window.failed')} failed")
        assert done > 0
    finally:
        await browser.close()

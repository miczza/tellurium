import http.server
import threading
import time
from pathlib import Path

import pytest

FIXTURES_DIR = str(Path(__file__).parent / "fixtures")


class _FixtureHandler(http.server.SimpleHTTPRequestHandler):
    """Static fixtures, plus two helpers:

    * ``/slow/<ms>/<name>`` — an empty 200 after a delay
    * ``/redirect/<path>`` — a 302 to ``/<path>``
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=FIXTURES_DIR, **kw)

    def do_GET(self):
        parts = self.path.split("/")
        if len(parts) >= 3 and parts[1] == "slow":
            time.sleep(int(parts[2]) / 1000)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if len(parts) >= 3 and parts[1] == "redirect":
            self.send_response(302)
            self.send_header("Location", "/" + "/".join(parts[2:]))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def local_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
async def browser():
    from tellurium import Browser

    b = await Browser.launch(headless=True)
    yield b
    await b.close()


@pytest.fixture
async def stealth_browser():
    from tellurium import Browser

    b = await Browser.launch(headless=True, stealth=True)
    yield b
    await b.close()

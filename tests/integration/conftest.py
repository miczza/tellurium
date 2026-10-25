import http.server
import threading
import time
import urllib.parse
from pathlib import Path

import pytest

FIXTURES_DIR = str(Path(__file__).parent / "fixtures")
DOWNLOAD_BODY = b"id,name\n1,tellurium\n"


class _FixtureHandler(http.server.SimpleHTTPRequestHandler):
    """Static fixtures, plus two helpers:

    * ``/slow/<ms>/<name>`` — an empty 200 after a delay
    * ``/redirect/<path>`` — a 302 to ``/<path>``
    * ``/download/<name>`` — an attachment named *name* (``DOWNLOAD_BODY``)
    * ``/download-slow/<name>`` — an attachment trickling for ~30 s
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
        if len(parts) >= 3 and parts[1] in ("download", "download-slow"):
            name = urllib.parse.unquote(parts[2])
            self._attachment(name, slow=parts[1] == "download-slow")
            return
        if len(parts) >= 3 and parts[1] == "redirect":
            self.send_response(302)
            self.send_header("Location", "/" + "/".join(parts[2:]))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        super().do_GET()

    def _attachment(self, name, slow):
        chunks = [b"x" * 1024] * 300 if slow else [DOWNLOAD_BODY]
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(sum(map(len, chunks))))
        self.end_headers()
        try:
            for chunk in chunks:
                self.wfile.write(chunk)
                self.wfile.flush()
                if slow:
                    time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the download was canceled

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


@pytest.fixture(scope="session")
def other_server():
    """The same fixtures from 127.0.0.2: a third site, next to 127.0.0.1 and localhost."""
    server = http.server.ThreadingHTTPServer(("127.0.0.2", 0), _FixtureHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.2:{port}"
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


@pytest.fixture(params=[False, True], ids=["plain", "stealth"])
async def any_browser(request):
    from tellurium import Browser

    b = await Browser.launch(headless=True, stealth=request.param)
    yield b
    await b.close()


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: soak tests, run only with TELLURIUM_SLOW=1")


def pytest_collection_modifyitems(config, items):
    import os

    if os.environ.get("TELLURIUM_SLOW") == "1":
        return
    skip = pytest.mark.skip(reason="soak test: set TELLURIUM_SLOW=1 to run it")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)

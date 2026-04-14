import http.server
import threading
from pathlib import Path
import pytest

FIXTURES_DIR = str(Path(__file__).parent / "fixtures")


@pytest.fixture(scope="session")
def local_server():
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(
        *a, directory=FIXTURES_DIR, **kw)
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
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

"""navigator.languages / Accept-Language parity with real Chrome under stealth."""

import http.server
import threading

import pytest


@pytest.fixture
def header_server():
    seen = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen["accept_language"] = self.headers.get("Accept-Language")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>ok</html>")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/", seen
    srv.shutdown()


async def test_languages_native_shape_under_stealth(header_server):
    from tellurium import Browser

    url, seen = header_server
    browser = await Browser.launch(headless=True, stealth=True, seed=1)
    async with browser:
        langs = browser._stealth_profile.languages
        tab = await browser.new_tab(url)
        js_langs = await tab.eval("Array.from(navigator.languages)")
        # Chrome 156+ exposes only the first language (Accept-Language reduction);
        # earlier versions the whole list: a non-empty prefix of the profile's.
        assert js_langs and js_langs == langs[: len(js_langs)]
        assert all(";" not in lang for lang in js_langs)
        header = seen["accept_language"]
        assert header.split(",")[0] == langs[0]
        assert ";q=0.9" in header or len(js_langs) == 1
        assert ", " not in header and ";q=0.9;q=0.9" not in header
        worker_langs = await tab.eval(
            "new Promise(r => { const w = new Worker(URL.createObjectURL(new Blob(["
            "'postMessage(JSON.stringify(Array.from(navigator.languages)))'])));"
            "w.onmessage = e => r(JSON.parse(e.data)); })"
        )
        assert worker_langs == js_langs

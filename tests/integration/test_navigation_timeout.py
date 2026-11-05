"""Navigation deadlines, errors and main-frame filtering (R1: M1, M11, m9).

A dedicated server holds ``/hang`` open until teardown and answers ``/204``
and ``/download``; every test runs under an outer guard so a regression fails
instead of hanging the suite.
"""

from __future__ import annotations

import asyncio
import http.server
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest

from tellurium.browser.navigation import NavigationError, NavigationTimeoutError

GUARD = 20
FIXTURES = str(Path(__file__).parent / "fixtures")


@pytest.fixture(scope="module")
def server():
    release = threading.Event()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=FIXTURES, **kw)

        def do_GET(self):
            if self.path == "/hang":
                release.wait(60)
                return
            if self.path == "/204":
                self.send_response(204)
                self.end_headers()
                return
            if self.path == "/download":
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename=x.bin")
                self.send_header("Content-Length", "3")
                self.end_headers()
                self.wfile.write(b"abc")
                return
            super().do_GET()

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    release.set()
    httpd.shutdown()


async def _guard(coro):
    return await asyncio.wait_for(coro, timeout=GUARD)


# ---------------------------------------------------------------------------
# M1 — one deadline covers Page.navigate and the wait
# ---------------------------------------------------------------------------


async def test_held_response_times_out_within_the_deadline(browser, server):
    tab = browser.main_tab
    start = time.monotonic()
    with pytest.raises(NavigationTimeoutError) as info:
        await _guard(tab.get(f"{server}/hang", timeout=2))
    assert time.monotonic() - start < 6
    err = info.value
    assert isinstance(err, TimeoutError)
    assert err.url == f"{server}/hang"
    assert err.phase == "commit"
    assert f"{server}/hang" in str(err)


async def test_tab_is_usable_after_a_navigation_timeout(browser, server):
    tab = browser.main_tab
    with pytest.raises(TimeoutError):
        await _guard(tab.get(f"{server}/hang", timeout=1))
    await _guard(tab.get(f"{server}/basic.html", timeout=10))
    assert tab.title == "Basic Test Page"


async def test_timeout_while_waiting_for_load_names_the_phase(browser, local_server):
    tab = browser.main_tab
    with pytest.raises(NavigationTimeoutError) as info:
        # 5 s: the commit fits even on a slow runner, the 12 s image does not
        await _guard(tab.get(f"{local_server}/slower_load.html", wait_until="load", timeout=5))
    assert info.value.phase == "load"
    assert "load" in str(info.value)


# ---------------------------------------------------------------------------
# m9 — errors that name the cause
# ---------------------------------------------------------------------------


async def test_no_content_response_raises_navigation_error_with_url(browser, server):
    tab = browser.main_tab
    with pytest.raises(NavigationError) as info:
        await _guard(tab.get(f"{server}/204", timeout=10))
    err = info.value
    assert isinstance(err, RuntimeError)
    assert err.url == f"{server}/204"
    assert err.error_text == "net::ERR_ABORTED"
    assert "download" in str(err)


async def test_download_raises_navigation_error(browser, server):
    with pytest.raises(NavigationError, match="ERR_ABORTED"):
        await _guard(browser.main_tab.get(f"{server}/download", timeout=10))


# ---------------------------------------------------------------------------
# M11 — wait_for_navigation follows the main frame only
# ---------------------------------------------------------------------------


async def test_wait_for_navigation_ignores_iframe_navigations(browser, server):
    tab = browser.main_tab
    await _guard(tab.get(f"{server}/basic.html"))
    waiter = asyncio.ensure_future(tab.wait_for_navigation(timeout=10))
    await tab.eval(
        "var f = document.createElement('iframe');"
        f"f.src = '{server}/form.html'; document.body.appendChild(f); 1"
    )
    await asyncio.sleep(1)
    assert not waiter.done(), "resolved on an iframe navigation"
    await tab.eval(f"location.href = '{server}/tree.html'; 1")
    await _guard(waiter)
    assert tab.url == f"{server}/tree.html"
    assert await tab.eval("document.readyState") == "complete"


async def test_wait_for_navigation_matches_the_url_pattern(browser, server):
    tab = browser.main_tab
    await _guard(tab.get(f"{server}/basic.html"))
    waiter = asyncio.ensure_future(tab.wait_for_navigation("*/tree.html", timeout=10))
    await tab.eval(f"location.href = '{server}/form.html'; 1")
    await asyncio.sleep(1)
    assert not waiter.done()
    await tab.eval(f"location.href = '{server}/tree.html'; 1")
    await _guard(waiter)
    assert tab.url.endswith("/tree.html")


async def test_wait_for_navigation_timeout_is_a_builtin_timeout_error(browser, server):
    tab = browser.main_tab
    await _guard(tab.get(f"{server}/basic.html"))
    with pytest.raises(NavigationTimeoutError) as info:
        await _guard(tab.wait_for_navigation("*/never*", timeout=0.5))
    assert isinstance(info.value, TimeoutError)
    assert "*/never*" in str(info.value)


async def test_wait_for_navigation_returns_on_a_back_forward_cache_restore(browser, server):
    tab = await _guard(browser.new_tab(f"{server}/basic.html"))
    await _guard(tab.get(f"{server}/tree.html"))
    waiter = asyncio.ensure_future(tab.wait_for_navigation(timeout=8))
    await asyncio.sleep(0.1)
    await tab.back()
    await _guard(waiter)
    assert tab.url == f"{server}/basic.html"


async def test_wait_for_navigation_waits_for_the_load_of_the_matching_document(
    browser, local_server
):
    tab = browser.main_tab
    await _guard(tab.get(f"{local_server}/basic.html"))
    waiter = asyncio.ensure_future(tab.wait_for_navigation("*redirect_final*", timeout=10))
    await tab.eval("location.href = '/redirect_step.html'; 1")
    await _guard(waiter)
    assert tab.url.endswith("/redirect_final.html")
    assert await tab.eval("document.readyState") == "complete"


# ---------------------------------------------------------------------------
# One deadline: cleanup and bookkeeping stay inside the caller's timeout
# ---------------------------------------------------------------------------

_DCL_ALERT = "data:text/html," + quote(
    "<p>x</p><script>"
    "addEventListener('DOMContentLoaded', () => setTimeout(() => alert('open'), 0));"
    "</script>"
)
_LOAD_ALERT = "data:text/html," + quote(
    "<p>x</p><script>addEventListener('load', () => alert('open'));</script>"
)


async def test_get_returns_within_timeout_when_the_page_freezes_after_commit(browser):
    tab = browser.main_tab
    tab._dialogs.policy = "manual"  # the alert stays open and freezes the page
    start = time.monotonic()
    await _guard(tab.get(_DCL_ALERT, wait_until="domcontentloaded", timeout=3))
    assert time.monotonic() - start < 3.5
    await tab._dialogs.last.dismiss()


async def test_timeout_with_a_frozen_page_stays_within_the_deadline(browser):
    tab = browser.main_tab
    tab._dialogs.policy = "manual"
    start = time.monotonic()
    with pytest.raises(NavigationTimeoutError) as info:
        await _guard(tab.get(_LOAD_ALERT, wait_until="load", timeout=2))
    assert time.monotonic() - start < 2.5
    assert "alert dialog is still open: 'open'" in str(info.value)
    await tab._dialogs.last.dismiss()

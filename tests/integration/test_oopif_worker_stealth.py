"""T7.7 §P1.1/§P1.2 — OOPIF freeze + worker-scope stealth injection.

Two HTTP servers on different *hostnames* are required: Chrome's site
isolation keys on site (scheme + eTLD+1), so 127.0.0.1:A and 127.0.0.1:B are
the same site and an iframe between them is cross-origin but *not* an OOPIF.
``--host-resolver-rules=MAP *.test 127.0.0.1`` gives us ``a.test`` /
``b.test``, which Chrome does isolate into separate processes.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import threading
import time

import pytest

RESOLVER_FLAG = "--host-resolver-rules=MAP *.test 127.0.0.1"

CHILD_HTML = b"""<html><body>child
<script>
  window.__probe = JSON.stringify({
    webdriver: navigator.webdriver,
    webdriverType: typeof navigator.webdriver,
    hc: navigator.hardwareConcurrency,
  });
</script></body></html>"""

WORKER_SRC = """
self.onmessage = () => {
  const n = self.navigator;
  postMessage(JSON.stringify({
    hc: n.hardwareConcurrency,
    hasWebdriver: ('webdriver' in n),
    webdriverType: typeof n.webdriver,
    toStr: Object.getOwnPropertyDescriptor(
      Object.getPrototypeOf(n), 'hardwareConcurrency').get.toString(),
    ctor: Object.getPrototypeOf(n).constructor.name,
  }));
};
"""


def _parent_html(child_port: int) -> bytes:
    src = json.dumps(WORKER_SRC)
    return f"""<html><body><h1>parent</h1>
<iframe id="f" src="http://b.test:{child_port}/child.html"></iframe>
<script>
window.__worker = null;
const src = {src};
const w = new Worker(URL.createObjectURL(new Blob([src], {{type: 'text/javascript'}})));
w.onmessage = (e) => {{ window.__worker = e.data; }};
setTimeout(() => w.postMessage(1), 150);
</script></body></html>""".encode()


class _Handler(http.server.BaseHTTPRequestHandler):
    body = b""

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):  # silence
        pass


def _serve(body: bytes) -> tuple[http.server.HTTPServer, int]:
    server = http.server.HTTPServer(
        ("127.0.0.1", 0),
        type("H", (_Handler,), {"body": body}),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


@pytest.fixture(scope="module")
def oopif_site():
    """Yield the parent-page URL served from a.test with a b.test iframe."""
    child_server, child_port = _serve(CHILD_HTML)
    parent_server, parent_port = _serve(_parent_html(child_port))
    try:
        yield f"http://a.test:{parent_port}/"
    finally:
        child_server.shutdown()
        parent_server.shutdown()


async def _iframe_probe(browser, tab) -> dict:
    """Read window.__probe from the OOPIF via its own auto-attached session."""
    targets = await browser._router.root.send("Target.getTargets", {})
    for info in targets.get("targetInfos", []):
        if info["type"] == "iframe" and "b.test" in info.get("url", ""):
            session = await browser._router.attach(info["targetId"])
            result = await session.send(
                "Runtime.evaluate",
                {
                    "expression": "window.__probe",
                    "returnByValue": True,
                },
            )
            return json.loads(result["result"]["value"])
    raise AssertionError("no OOPIF target for b.test found")


@pytest.mark.asyncio
async def test_oopif_and_worker_are_patched(oopif_site):
    from tellurium import Browser

    browser = await Browser.launch(
        headless=True,
        stealth=True,
        args=[RESOLVER_FLAG],
    )
    try:
        tab = browser.main_tab
        await tab.get(oopif_site)
        await asyncio.sleep(1.5)

        # --- P1.1: cross-origin iframe (OOPIF) --------------------------
        iframe = await _iframe_probe(browser, tab)
        assert iframe["webdriver"] is False, f"OOPIF navigator.webdriver not patched: {iframe}"

        # --- P1.2: worker scope -----------------------------------------
        raw = await tab.eval("window.__worker")
        assert raw, "worker never answered (possible waitForDebugger deadlock)"
        worker = json.loads(raw)

        window_hc = await tab.eval("navigator.hardwareConcurrency")
        assert worker["hc"] == window_hc, (
            "window/worker hardwareConcurrency mismatch "
            f"(window={window_hc}, worker={worker['hc']}) — design doc 04 §P1.2"
        )
        # The spoofed getter must still look native.
        assert worker["toStr"] == ("function get hardwareConcurrency() { [native code] }")
        # navigator.webdriver does not exist on WorkerNavigator in real
        # Chrome — defining it would be a new fingerprint, not a fix.
        assert worker["ctor"] == "WorkerNavigator"
        assert worker["hasWebdriver"] is False
        assert worker["webdriverType"] == "undefined"
    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_freezing_targets_does_not_slow_navigation(oopif_site):
    """waitForDebuggerOnStart must not cost more than 10% (+15 ms) on new_tab+get.

    The comparison is stealth-with-freeze vs stealth-without-freeze (the
    pre-T7.7 auto-attach configuration), so it isolates the cost of the
    freeze itself rather than re-measuring the whole stealth pipeline.
    """
    import statistics

    from tellurium import Browser
    from tellurium.stealth.engine import _STEALTH_TARGET_FILTER, StealthEngine

    frozen = StealthEngine.setup_auto_attach

    async def unfrozen(self, session, *, include_pages=False):
        # Pages stay auto-attached (Browser adopts tabs through it); only
        # the freeze is switched off.
        target_filter = list(_STEALTH_TARGET_FILTER)
        if include_pages:
            target_filter.append({"type": "page", "exclude": False})
        await session.send(
            "Target.setAutoAttach",
            {
                "autoAttach": True,
                "waitForDebuggerOnStart": False,
                "flatten": True,
                "filter": target_filter,
            },
        )

    async def _measure() -> float:
        browser = await Browser.launch(
            headless=True,
            stealth=True,
            args=[RESOLVER_FLAG],
        )
        try:
            await browser.new_tab(oopif_site)  # warm-up
            samples = []
            for _ in range(6):
                start = time.monotonic()
                await browser.new_tab(oopif_site)
                samples.append(time.monotonic() - start)
            return statistics.median(samples)
        finally:
            await browser.close()

    # Interleave the two configurations to even out machine drift, and judge
    # the median over several rounds: a single pair of runs flips on a loaded
    # machine (parallel test runs), where a few ms of jitter exceed 10%.
    baselines: list[float] = []
    freezes: list[float] = []
    try:
        for _ in range(3):
            StealthEngine.setup_auto_attach = unfrozen
            baselines.append(await _measure())
            StealthEngine.setup_auto_attach = frozen
            freezes.append(await _measure())
    finally:
        StealthEngine.setup_auto_attach = frozen

    baseline = statistics.median(baselines)
    stealthy = statistics.median(freezes)
    # 10% plus an absolute 15 ms floor: below that the difference is noise,
    # while a freeze that stalls the target costs far more.
    assert stealthy <= baseline * 1.10 + 0.015, (
        f"freeze regressed new_tab+navigate: {stealthy * 1000:.1f}ms vs {baseline * 1000:.1f}ms"
    )

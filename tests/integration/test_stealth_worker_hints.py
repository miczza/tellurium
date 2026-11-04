"""Service and shared workers under stock stealth: the same client hints as the
page, and patched before their own script runs.

Stock stealth launches Chrome with ``--user-agent``; with it Chrome leaves the
high-entropy hints of a worker empty unless the worker's own target gets the
override (a dedicated worker inherits the page's). A service worker frozen at
start answers no command until it runs, so a patch awaited before the resume
used to stall it for 10 s and land after its script.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tellurium import Browser
from tests.integration.test_robots import SiteProxy

pytestmark = pytest.mark.asyncio

HIGH = "['architecture', 'bitness', 'fullVersionList', 'uaFullVersion', 'platformVersion']"
JS = {"Content-Type": "application/javascript"}
# Read at the top of each worker's script: what it sees before anything else.
TOP = f"""
const seen = navigator.userAgentData.getHighEntropyValues({HIGH})
  .then(v => JSON.stringify({{...v, cores: navigator.hardwareConcurrency}}));
"""
SERVICE = (
    TOP
    + """
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(clients.claim()));
self.onmessage = e => seen.then(v => e.ports[0].postMessage(v));
"""
).encode()
SHARED = (TOP + "onconnect = e => seen.then(v => e.ports[0].postMessage(v));").encode()
ASK_PAGE = (
    f"navigator.userAgentData.getHighEntropyValues({HIGH})"
    ".then(v => JSON.stringify({...v, cores: navigator.hardwareConcurrency}))"
)
ASK_SERVICE = """navigator.serviceWorker.register('/sw.js')
  .then(() => navigator.serviceWorker.ready)
  .then(reg => new Promise(r => {
    const c = new MessageChannel();
    c.port1.onmessage = e => r(e.data);
    reg.active.postMessage('ask', [c.port2]);
  }))"""
ASK_SHARED = """new Promise(r => {
  const w = new SharedWorker('/shared.js');
  w.port.onmessage = e => r(e.data);
  w.port.start();
})"""


@pytest.mark.parametrize("headless", [True, False], ids=["headless", "headed"])
async def test_service_and_shared_workers_have_the_page_client_hints(headless):
    routes = {
        "/page": (200, {"Content-Type": "text/html"}, b"<!doctype html><p>ok"),
        "/sw.js": (200, JS, SERVICE),
        "/shared.js": (200, JS, SHARED),
    }
    async with SiteProxy(routes) as site:  # straight from 127.0.0.1: a secure context
        browser = await Browser.launch(headless=headless, stealth=True)
        try:
            tab = await browser.new_tab()
            await tab.get(site.url + "/page", timeout=15)
            page = json.loads(await tab.eval(ASK_PAGE))
            shared = json.loads(await tab.eval(ASK_SHARED, timeout=10))
            loop = asyncio.get_running_loop()
            started = loop.time()
            service = json.loads(await tab.eval(ASK_SERVICE, timeout=20))
            service_took = loop.time() - started
        finally:
            await browser.close()
    assert page["architecture"] and page["bitness"] and page["fullVersionList"]
    for name, values in (("shared", shared), ("service", service)):
        for key in ("architecture", "bitness", "fullVersionList", "uaFullVersion", "brands"):
            assert values[key] == page[key], (name, key, values[key], page[key])
        assert values["cores"] == page["cores"], (name, "patched before its script")
    assert service_took < 5, f"the service worker started after {service_took:.1f} s"

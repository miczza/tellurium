"""R3-B diagnosis (temporary): the three CI reds in a loop, probes on a hang."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

from tellurium import Browser
from tellurium.cdp.transport._session import SessionRouter
from tests.integration.test_robots import ROBOTS, SiteProxy, _load
from tests.integration.test_tab_screenshot import _TALL_BODY, _check_full_page, _emulate

pytestmark = pytest.mark.asyncio

N = int(os.environ.get("R3_DIAG_N", "30"))
_ARGS = ["--enable-logging=stderr", "--v=0"]


class Clock:
    def __init__(self):
        self.t0 = time.monotonic()
        self.steps: list[str] = []

    def mark(self, what: str) -> None:
        self.steps.append(f"{time.monotonic() - self.t0:7.2f}s {what}")


async def _try(label, coro, out):
    t = time.monotonic()
    try:
        res = await coro
        out.append(f"  probe {label}: ok in {time.monotonic() - t:.2f}s -> {str(res)[:300]}")
    except BaseException as e:  # noqa: BLE001
        out.append(f"  probe {label}: {type(e).__name__} {e} after {time.monotonic() - t:.2f}s")


async def _probes(browser, session, out, retry=None):
    root = browser._router.root
    await _try("root Browser.getVersion", root.send("Browser.getVersion", {}, timeout=5), out)
    await _try("root Target.getTargets", root.send("Target.getTargets", {}, timeout=5), out)
    if session is not None:
        ev = {
            "expression": "[document.visibilityState, document.hasFocus(), location.href,"
            " document.readyState, performance.now()]",
            "returnByValue": True,
        }
        await _try("session Runtime.evaluate", session.send("Runtime.evaluate", ev, timeout=5), out)
        await _try(
            "raf",
            session.send(
                "Runtime.evaluate",
                {
                    "expression": "new Promise(r => requestAnimationFrame(() => r(performance.now())))",
                    "awaitPromise": True,
                    "returnByValue": True,
                },
                timeout=5,
            ),
            out,
        )
        await _try(
            "Page.captureScreenshot viewport",
            session.send("Page.captureScreenshot", {"format": "png"}, timeout=10),
            out,
        )
    if retry is not None:
        await _try("retry", retry(), out)


def _report(clock, out, log: Path, exc):
    lines = [f"FAILED: {type(exc).__name__}: {exc}", *clock.steps, *out]
    try:
        tail = log.read_bytes().decode(errors="replace").splitlines()[-80:]
    except OSError as e:
        tail = [f"(no log: {e})"]
    lines += ["--- chrome log tail ---", *tail]
    print("\n".join(lines))
    sys.stdout.flush()


def _log_path() -> Path:
    fd, p = tempfile.mkstemp(prefix="r3diag_", suffix=".log")
    os.close(fd)
    return Path(p)


@pytest.mark.parametrize("i", range(N))
async def test_diag_launch_attach(i, monkeypatch):
    """Red 4: Target.attachToTarget at launch."""
    clock, out, log = Clock(), [], _log_path()
    real = SessionRouter.attach
    state = {}

    async def attach(self, target_id, **kw):
        clock.mark(f"attach {target_id}")
        try:
            s = await real(self, target_id, via=kw.get("via"), timeout=kw.get("timeout") or 15)
            clock.mark("attached")
            return s
        except TimeoutError as e:
            clock.mark("attach TIMEOUT")
            r = self.root
            await _try("root Browser.getVersion", r.send("Browser.getVersion", {}, timeout=5), out)
            await _try("root Target.getTargets", r.send("Target.getTargets", {}, timeout=5), out)
            await _try(
                "root Target.getTargetInfo",
                r.send("Target.getTargetInfo", {"targetId": target_id}, timeout=5),
                out,
            )
            await _try("attach again", real(self, target_id, timeout=20), out)
            state["exc"] = e
            raise

    monkeypatch.setattr(SessionRouter, "attach", attach)
    clock.mark("launch")
    try:
        b = await Browser.launch(headless=True, chrome_log=log, args=_ARGS)
    except Exception as e:
        _report(clock, out, log, e)
        raise
    clock.mark("launched")
    await b.close()


@pytest.mark.parametrize("i", range(N))
async def test_diag_screenshot(i):
    """Red 5: full page capture at ratio 2 before the first navigation."""
    clock, out, log = Clock(), [], _log_path()
    b = await Browser.launch(headless=True, chrome_log=log, args=_ARGS)
    clock.mark("launched")
    try:
        tab = b.main_tab
        await tab.eval(_TALL_BODY)
        clock.mark("body")
        await _emulate(tab, 2)
        clock.mark("emulated")
        try:
            await _check_full_page(tab)
            clock.mark("checked")
        except Exception as e:
            clock.mark("FAILED")

            async def retry():
                return len(
                    (
                        await tab._session.send(
                            "Page.captureScreenshot",
                            {"format": "png", "captureBeyondViewport": True},
                            timeout=30,
                        )
                    )["data"]
                )

            await _probes(b, tab._session, out, retry)
            _report(clock, out, log, e)
            raise
    finally:
        await b.close()


@pytest.mark.parametrize("i", range(N))
async def test_diag_load_network_resource(i):
    """Red 6: Network.loadNetworkResource through a proxy from about:blank, stealth."""
    clock, out, log = Clock(), [], _log_path()
    routes = {
        "/robots.txt": (301, {"Location": "http://site.test/real-robots.txt"}, b""),
        "/real-robots.txt": (200, {"Content-Type": "text/plain"}, ROBOTS),
    }
    async with SiteProxy(routes) as proxy:
        clock.mark("launch")
        b = await Browser.launch(
            headless=True, stealth=True, proxy=proxy.url, chrome_log=log, args=_ARGS
        )
        clock.mark("launched")
        try:
            tab = await b.new_tab()
            clock.mark(f"new_tab frame={tab._frame_id!r} target={tab._target_id}")
            try:
                res = await _load(tab, "http://site.test/robots.txt")
                clock.mark("loaded")
                assert res["success"], res
            except Exception as e:
                clock.mark("FAILED")
                out.append(f"  proxy seen: {[line for line, _ in proxy.seen]}")

                async def retry():
                    return await _load(tab, "http://site.test/robots.txt?again")

                await _probes(b, tab._session, out, retry)
                out.append(f"  proxy seen after: {[line for line, _ in proxy.seen]}")
                _report(clock, out, log, e)
                raise
        finally:
            await b.close()

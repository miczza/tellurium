"""What a click on the banner's "Done" met, for the message of a test that
saw it lost: the window, the page's visibility and viewport, and the input
events that reached the document (seen from an isolated world of the probe,
so the page and the banner see nothing of it)."""

from __future__ import annotations

import json
import time

_WORLD = "__tl_banner_probe"

_LISTEN_JS = """
(function () {
  if (globalThis.__probe) return 'again';
  const log = globalThis.__probe = [];
  const t0 = performance.now();
  const note = function (what) { log.push(Math.round(performance.now() - t0) + 'ms ' + what); };
  for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click', 'submit']) {
    window.addEventListener(type, function (e) {
      const t = e.target;
      note(type + ' trusted=' + e.isTrusted + ' at=' + e.clientX + ',' + e.clientY +
           ' target=' + (t && (t.nodeName || t)) +
           ' active=' + navigator.userActivation.isActive);
    }, true);
  }
  for (const type of ['visibilitychange', 'focus', 'blur', 'resize', 'pagehide', 'pageshow']) {
    (type === 'visibilitychange' ? document : window).addEventListener(type, function () {
      note(type + ' vis=' + document.visibilityState + ' focus=' + document.hasFocus() +
           ' inner=' + innerWidth + 'x' + innerHeight);
    }, true);
  }
  return 'ok';
})()
"""

_STATE_JS = """
(async function (x, y) {
  const hit = document.elementFromPoint(x, y);
  // Whether the page renders: a frame within 500 ms, and its paint entries.
  const t = performance.now();
  const frame = await Promise.race([
    new Promise(function (r) { requestAnimationFrame(function () { r(performance.now() - t); }); }),
    new Promise(function (r) { setTimeout(function () { r('none in 500ms'); }, 500); }),
  ]);
  return JSON.stringify({
    frame: frame, now: Math.round(performance.now()),
    paints: performance.getEntriesByType('paint').map(function (e) {
      return e.name + '@' + Math.round(e.startTime);
    }),
    vis: document.visibilityState, focus: document.hasFocus(), ready: document.readyState,
    url: location.href, inner: [innerWidth, innerHeight], outer: [outerWidth, outerHeight],
    screen: [screenX, screenY], dpr: devicePixelRatio,
    hit: hit && hit.nodeName, popovers: document.querySelectorAll(':popover-open').length,
    log: globalThis.__probe || null,
  });
})(%s, %s)
"""


class BannerProbe:
    """Attached to a tab just before the click at (*x*, *y*)."""

    def __init__(self, tab, x: float, y: float) -> None:
        self.tab = tab
        self.x, self.y = x, y
        self.context: int | None = None
        self.notes: list[str] = []
        self.t0 = time.monotonic()

    async def attach(self) -> None:
        self.notes.append("before: " + await self._state())
        try:
            tree = await self.tab.send_cdp("Page.getFrameTree", {})
            world = await self.tab.send_cdp(
                "Page.createIsolatedWorld",
                {"frameId": tree["frameTree"]["frame"]["id"], "worldName": _WORLD},
            )
            self.context = world["executionContextId"]
            await self._eval(_LISTEN_JS)
        except Exception as exc:  # noqa: BLE001 - a probe never fails the test itself
            self.notes.append(f"listen: {exc!r}")

    def sent(self, kind: str, reply) -> None:
        self.notes.append(f"{time.monotonic() - self.t0:.3f}s {kind} -> {reply!r}")

    async def report(self) -> str:
        """The notes, and the state now."""
        self.notes.append("after: " + await self._state())
        notes = "\n  ".join(self.notes)
        return f"lost click on the banner at ({self.x:.1f}, {self.y:.1f}):\n  {notes}"

    async def _state(self) -> str:
        parts: dict = {}
        try:
            parts["page"] = json.loads(await self._eval(_STATE_JS % (self.x, self.y)))
        except Exception as exc:  # noqa: BLE001
            parts["page"] = repr(exc)
        try:
            root = self.tab._browser._router.root
            win = await root.send(
                "Browser.getWindowForTarget", {"targetId": self.tab._target_id}, timeout=5
            )
            parts["window"] = win
        except Exception as exc:  # noqa: BLE001
            parts["window"] = repr(exc)
        try:
            metrics = await self.tab.send_cdp("Page.getLayoutMetrics", {})
            parts["layout"] = metrics.get("cssLayoutViewport")
            parts["visual"] = metrics.get("cssVisualViewport")
        except Exception as exc:  # noqa: BLE001
            parts["layout"] = repr(exc)
        try:
            targets = await self.tab._browser._router.root.send("Target.getTargets", {}, timeout=5)
            parts["pages"] = [
                (t["targetId"][:6], t["url"][:40], t.get("attached"))
                for t in targets["targetInfos"]
                if t["type"] == "page"
            ]
        except Exception as exc:  # noqa: BLE001
            parts["pages"] = repr(exc)
        parts["parity_done"] = getattr(self.tab, "_screen_parity_done", None)
        return json.dumps(parts, default=str)

    async def _eval(self, expression: str):
        params = {"expression": expression, "returnByValue": True, "awaitPromise": True}
        if self.context is not None:
            params["contextId"] = self.context
        reply = await self.tab.send_cdp("Runtime.evaluate", params)
        return reply.get("result", {}).get("value")


_probes: dict[int, BannerProbe] = {}


async def probed_click(tab, x: float, y: float) -> None:
    """``tab.mouse_click(x, y)`` with a probe on, for :func:`report`."""
    probe = BannerProbe(tab, x, y)
    _probes[id(tab)] = probe
    await probe.attach()
    await tab.mouse_click(x, y)
    probe.sent("click", None)


async def report(tab) -> str:
    probe = _probes.get(id(tab))
    if probe is None:
        return "no click probed on this tab"
    return await probe.report()

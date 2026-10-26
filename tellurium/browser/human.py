"""Handing a tab over to a person: :func:`wait_for_human`.

In headed Chrome a banner tells the person why the script stopped and offers a
"Done" button. The banner lives in a closed shadow root built from an isolated
world, so the page can neither read nor style it, and it is put back after
every navigation (or if the page removes it). "Done" reaches tellurium through
a CDP binding that exists only in that isolated world and is called only for a
trusted click: the page cannot pretend the person has finished. In headless
Chrome there is nobody to click, so only the condition (*until*) ends the wait.
"""

from __future__ import annotations

import asyncio
import json
import math
import secrets
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from tellurium.browser.navigation import url_matches
from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.tab import Tab

#: What ends a wait besides "Done": a URL pattern (see :func:`url_matches`) or
#: an async callable taking the tab and returning a truthy value when done.
Until = str | Callable[["Tab"], Awaitable[Any]] | None

#: Seconds between two checks of the condition (and of the banner).
POLL = 0.3
#: Bound on each CDP call: a hung tab must not stall the wait past its timeout.
CALL_TIMEOUT = 5.0
DONE_LABEL = "Done"

# Run in the banner's isolated world: (re)build the banner unless it is
# already in the document. Returns false when there is no document yet.
_SHOW_JS = """
(function (reason, done, label) {
  const call = globalThis[done];
  if (typeof call !== 'function') return false;
  const old = globalThis.__tlBanner;
  if (old && old.isConnected) return true;
  const root = document.documentElement;
  if (!root) return false;
  const host = document.createElement('div');
  const place = {all: 'initial', position: 'fixed', top: '0', left: '0', right: '0',
                 display: 'block', 'z-index': '2147483647'};
  for (const k in place) host.style.setProperty(k, place[k], 'important');
  const shadow = host.attachShadow({mode: 'closed'});
  const style = document.createElement('style');
  style.textContent = '.bar{display:flex;align-items:center;gap:12px;padding:10px 16px;' +
    'background:#1f2933;color:#f5f7fa;font:14px/1.4 system-ui,sans-serif;' +
    'box-shadow:0 2px 8px rgba(0,0,0,.35)}' +
    '.reason{flex:1;white-space:pre-wrap}' +
    'button{font:600 14px system-ui,sans-serif;padding:6px 18px;border:0;' +
    'border-radius:4px;background:#3ebd93;color:#102a2a;cursor:pointer}';
  const bar = document.createElement('div');
  bar.className = 'bar';
  const text = document.createElement('span');
  text.className = 'reason';
  text.textContent = reason;
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.addEventListener('click', function (event) {
    if (event.isTrusted) call('done');
  });
  bar.append(text, button);
  shadow.append(style, bar);
  root.appendChild(host);
  globalThis.__tlBanner = host;
  return true;
})(%s, %s, %s)
"""

_HIDE_JS = (
    "(function () { const h = globalThis.__tlBanner;"
    " if (h) h.remove(); globalThis.__tlBanner = null; return true; })()"
)


async def wait_for_human(
    tab: Tab, reason: str, *, until: Until = None, timeout: float | None = 600
) -> None:
    """Wait for a person to do something in *tab* (solve a captcha, sign in).

    Headed: a banner shows *reason* and a "Done" button; the wait ends when
    the person clicks it or *until* holds. Headless: no banner, *until* is
    required (``ValueError`` otherwise). *until* is a URL pattern (glob with
    ``*``/``?``, substring otherwise), matched against the main frame's URL
    as Chrome reports it, or an async callable ``(tab) -> bool``. On expiry
    of *timeout* seconds (``None``: no limit) ``TimeoutError`` names
    *reason*. The banner is removed on every way out, cancellation included.
    """
    check = _condition(until)
    headless = await _headless(tab)
    if headless and check is None:
        raise ValueError("wait_for_human in headless Chrome needs until=: nobody can click Done")
    loop = asyncio.get_running_loop()
    deadline = math.inf if timeout is None else loop.time() + timeout
    banner = None if headless else _Banner(tab, reason)
    try:
        if banner is not None:
            banner.open()
        while True:
            frame = await _main_frame(tab)
            if banner is not None and banner.done.is_set():
                return
            if frame is not None:  # None: the page is busy, look again next round
                if check is not None and await _bounded(check(tab, frame), deadline, reason):
                    return
                if banner is not None:
                    await banner.show(frame)
            left = deadline - loop.time()
            if left <= 0:
                raise _timeout(reason, timeout)
            if banner is None:
                await asyncio.sleep(min(POLL, left))
            elif await _clicked(banner.done, min(POLL, left)):
                return
    finally:
        if banner is not None:
            await banner.close()


def _condition(until: Until) -> Callable[[Tab, dict], Awaitable[bool]] | None:
    if until is None:
        return None
    if isinstance(until, str):
        pattern = until

        async def url_holds(tab: Tab, frame: dict) -> bool:
            return url_matches(pattern, frame.get("url", "") + frame.get("urlFragment", ""))

        return url_holds
    if callable(until):
        condition = until

        async def holds(tab: Tab, frame: dict) -> bool:
            return bool(await condition(tab))

        return holds
    raise TypeError(f"until must be a URL pattern or an async callable, not {until!r}")


async def _headless(tab: Tab) -> bool:
    """Whether *tab*'s Chrome is headless: the stealth engine knows, else
    Chrome's own user agent (the browser's, not a tab's override) says so."""
    engine = getattr(tab._browser, "_stealth_engine", None)
    if engine is not None:
        return bool(engine._headless)
    info = await tab._browser._router.root.send("Browser.getVersion", {}, timeout=CALL_TIMEOUT)
    return "HeadlessChrome" in info.get("userAgent", "")


async def _main_frame(tab: Tab) -> dict | None:
    """The main frame as Chrome reports it; ``None`` if the page is too busy to say."""
    try:
        tree = await tab._session.send("Page.getFrameTree", {}, timeout=CALL_TIMEOUT)
    except asyncio.TimeoutError:
        return None
    return tree["frameTree"]["frame"]


async def _bounded(awaitable: Awaitable[bool], deadline: float, reason: str) -> bool:
    """*awaitable*'s result, or the wait's ``TimeoutError`` past *deadline*."""
    left = deadline - asyncio.get_running_loop().time()
    if left == math.inf:
        return await awaitable
    try:
        return await asyncio.wait_for(awaitable, max(left, 0))
    except asyncio.TimeoutError:
        if asyncio.get_running_loop().time() >= deadline:
            raise _timeout(reason, None) from None
        raise


async def _clicked(done: asyncio.Event, seconds: float) -> bool:
    try:
        await asyncio.wait_for(done.wait(), seconds)
    except asyncio.TimeoutError:
        return False
    return True


def _timeout(reason: str, timeout: float | None) -> TimeoutError:
    within = "" if timeout is None else f" within {timeout:g} s"
    return TimeoutError(f"wait_for_human({reason!r}) did not end{within}")


class _Banner:
    """The banner of one wait: an isolated world per document, the "Done"
    binding in it (a fresh name per wait), and the event that it was clicked."""

    def __init__(self, tab: Tab, reason: str) -> None:
        token = secrets.token_hex(8)
        self._session = tab._session
        self._reason = reason
        self._world = f"__tl_human_{token}"
        self._binding = f"__tl_done_{token}"
        self._context: int | None = None
        self._loader: str | None = None  # the document the context belongs to
        self._bound = False
        self.done = asyncio.Event()

    def _on_binding(self, params: dict) -> None:
        if params.get("name") == self._binding:
            self.done.set()

    def open(self) -> None:
        self._session.on("Runtime.bindingCalled", self._on_binding)

    async def show(self, frame: dict) -> None:
        """Make sure the current document shows the banner."""
        try:
            if self._context is None or frame.get("loaderId") != self._loader:
                self._context = None
                world = await self._send(
                    "Page.createIsolatedWorld",
                    {
                        "frameId": frame["id"],
                        "worldName": self._world,
                        "grantUniversalAccess": False,
                    },
                )
                # Chrome installs a named binding only in the contexts that
                # exist when it is added: once per new document.
                await self._send(
                    "Runtime.addBinding",
                    {"name": self._binding, "executionContextName": self._world},
                )
                self._bound = True
                self._context, self._loader = world["executionContextId"], frame.get("loaderId")
            expression = _SHOW_JS % (
                json.dumps(self._reason),
                json.dumps(self._binding),
                json.dumps(DONE_LABEL),
            )
            await self._evaluate(expression)
        except asyncio.TimeoutError:
            pass  # a busy page: the same world next round (a new one would show a second banner)
        except (CDPError, KeyError):
            self._context = None  # the document went meanwhile: a new world next round

    async def close(self) -> None:
        """Take the banner out and the binding away; never raises (the tab may be gone)."""
        self._session.off("Runtime.bindingCalled", self._on_binding)
        if self._context is not None:
            try:
                await self._evaluate(_HIDE_JS)
            except Exception:  # noqa: BLE001 - document or tab gone: nothing left to hide
                pass
        if self._bound:
            try:
                await self._send("Runtime.removeBinding", {"name": self._binding})
            except Exception:  # noqa: BLE001 - tab gone
                pass

    async def _evaluate(self, expression: str) -> Any:
        params = {"expression": expression, "contextId": self._context, "returnByValue": True}
        resp = await self._send("Runtime.evaluate", params)
        return resp.get("result", {}).get("value")

    async def _send(self, method: str, params: dict) -> dict:
        return await self._session.send(method, params, timeout=CALL_TIMEOUT)

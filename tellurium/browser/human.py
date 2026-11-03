"""Handing a tab over to a person: :func:`wait_for_human`.

In headed Chrome a banner tells the person why the script stopped and offers a
"Done" button. The banner lives in a closed shadow root built from an isolated
world, so the page cannot read it, and every round it is put back, restyled,
kept in the top layer and moved where its button can be clicked (see
``_SHOW_JS``). "Done" reaches tellurium through a CDP binding that exists only
in that isolated world and is called only for a person's input: no script or
synthetic event of the page fires it. A hostile page can still block it (it
cancels the clicks on the banner, or hides it faster than a round) or trick
the person into it (it makes the banner invisible and lays it over a button of
its own, so the person's real click lands on "Done"): "Done" says that the
person clicked, not that the task is done. The README says how far this goes.
In headless Chrome there is nobody to click, so only the condition (*until*)
ends the wait.
"""

from __future__ import annotations

import asyncio
import json
import logging
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

logger = logging.getLogger("tellurium")

#: Seconds between two checks of the condition (and of the banner).
POLL = 0.3
#: Bound on each CDP call, cut to what is left of the wait when that is less.
CALL_TIMEOUT = 5.0
#: Least time a CDP call is given when the wait's deadline is nearer.
MIN_CALL = 0.05
#: How long the banner's cleanup holds up a wait that ran out of time; on a
#: busy page the rest goes on in the background, each call bounded.
CLEANUP_GRACE = 0.5
DONE_LABEL = "Done"

# Background work of the waits that are over (cleanup, a late early script):
# held here so that it is not collected before it ends.
_background: set[asyncio.Future] = set()

# Run in the banner's isolated world, at every new document (before the
# page's own scripts) and again every round of the wait. It (1) puts a click
# listener on window in the capture phase, so on a document loaded during the
# wait it runs before anything of the page; (2) builds the banner if it is
# not in the document; (3) puts back its style and its place in the top layer
# and, if its button is not what a click there would hit (hidden, covered,
# inert under a modal dialog), moves it on top or into the modal dialog.
# "unbound": the binding is missing from this world; "nodoc": no document
# yet; "blocked": the button cannot be made reachable this round.
_SHOW_JS = """
(function (reason, done, label) {
  const call = function () {
    const binding = globalThis[done];
    if (typeof binding === 'function') binding('done');
  };
  if (!globalThis.__tlGuard) {
    globalThis.__tlGuard = true;
    window.addEventListener('click', function (event) {
      const b = globalThis.__tlBanner;
      if (!event.isTrusted || !b || event.target !== b.host) return;
      const r = b.button.getBoundingClientRect();
      if (event.clientX >= r.left && event.clientX <= r.right &&
          event.clientY >= r.top && event.clientY <= r.bottom) call();
    }, true);
  }
  if (typeof globalThis[done] !== 'function') return 'unbound';
  const root = document.documentElement;
  if (!root) return 'nodoc';
  // Inline CSSOM styles: a style-src CSP blocks <style>, not these.
  const dress = function (el, props, important) {
    for (const k in props) el.style.setProperty(k, props[k], important ? 'important' : '');
  };
  const HOST = {all: 'initial', position: 'fixed', top: '0', left: '0', right: '0',
                display: 'block', visibility: 'visible', opacity: '1',
                'pointer-events': 'auto', 'z-index': '2147483647'};
  // HTML elements even in an SVG or XML document (createElement makes no
  // HTML there, and attachShadow would throw): the top layer shows them.
  const make = function (tag) {
    return document.createElementNS('http://www.w3.org/1999/xhtml', tag);
  };
  const build = function () {
    const host = make('div');
    const shadow = host.attachShadow({mode: 'closed'});
    // A form: its submit event is not composed, so it never leaves the shadow
    // root and no listener of the page can stop it.
    const form = make('form');
    form.method = 'dialog';
    dress(form, {display: 'flex', 'align-items': 'center', gap: '12px', margin: '0',
                 padding: '10px 16px', background: '#1f2933', color: '#f5f7fa',
                 font: '14px/1.4 system-ui, sans-serif',
                 'box-shadow': '0 2px 8px rgba(0,0,0,.35)'});
    const text = make('span');
    dress(text, {flex: '1', 'white-space': 'pre-wrap'});
    text.textContent = reason;
    const button = make('button');
    button.type = 'submit';
    button.textContent = label;
    dress(button, {font: '600 14px system-ui, sans-serif', padding: '6px 18px', border: '0',
                   'border-radius': '4px', background: '#3ebd93', color: '#102a2a',
                   cursor: 'pointer'});
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      // Only a person's input gives the window a transient activation:
      // click(), requestSubmit() or a synthetic event do not.
      if (navigator.userActivation.isActive) call();
    });
    form.append(text, button);
    shadow.append(form);
    return {host: host, shadow: shadow, button: button, css: null};
  };
  const raise = function (host) {
    try {
      if (host.matches(':popover-open')) host.hidePopover();
      host.showPopover();
    } catch (e) { /* not connected or not a popover: next round */ }
  };
  const reachable = function (b) {
    const r = b.button.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) return false;
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (document.elementFromPoint(x, y) !== b.host) return false;
    if (b.shadow.elementFromPoint(x, y) !== b.button) return false;
    return b.host.checkVisibility({opacityProperty: true, visibilityProperty: true});
  };
  let b = globalThis.__tlBanner;
  if (!b || !b.host.isConnected) {
    if (b) b.host.remove();
    b = globalThis.__tlBanner = build();
    root.appendChild(b.host);
  }
  if (b.host.style.cssText !== b.css) {
    b.host.style.cssText = '';
    dress(b.host, HOST, true);
    b.css = b.host.style.cssText;
  }
  if (b.host.getAttribute('popover') !== 'manual') b.host.setAttribute('popover', 'manual');
  if (b.host.inert) b.host.inert = false;
  if (!b.host.matches(':popover-open')) raise(b.host);
  if (reachable(b)) return 'shown';
  // Inert under a modal dialog of the page: only the dialog's subtree is not.
  const places = [root].concat(Array.from(document.querySelectorAll('dialog:modal')).reverse());
  for (const place of places) {
    if (b.host.parentNode !== place) place.appendChild(b.host);
    raise(b.host);
    if (reachable(b)) return 'shown';
  }
  return 'blocked';
})(%s, %s, %s)
"""

_HIDE_JS = (
    "(function () { const b = globalThis.__tlBanner;"
    " if (b) b.host.remove(); globalThis.__tlBanner = null; return true; })()"
)


async def wait_for_human(
    tab: Tab, reason: str, *, until: Until = None, timeout: float | None = 600
) -> None:
    """Wait for a person to do something in *tab* (solve a captcha, sign in).

    Headed: a banner shows *reason* and a "Done" button; the wait ends when
    the person clicks it or *until* holds. Headless: no banner, *until* is
    required (``ValueError`` otherwise). *until* is a URL pattern (glob with
    ``*``/``?``, substring otherwise), matched against the main frame's URL
    without query and fragment (``**/dashboard`` does not match
    ``/login?next=/dashboard`` nor ``/#/dashboard``), or an async callable
    ``(tab) -> bool``. On expiry of *timeout* seconds (``None``: no limit)
    ``TimeoutError`` names *reason*; it comes within about *timeout* even
    on a busy page, as every CDP call takes at most what is left. The banner
    is removed on every way out, cancellation included (on a page too busy
    to answer at once, just after the wait is over).
    """
    check = _condition(until)
    loop = asyncio.get_running_loop()
    deadline = math.inf if timeout is None else loop.time() + timeout
    headless = await _headless(tab, deadline)
    if headless and check is None:
        raise ValueError("wait_for_human in headless Chrome needs until=: nobody can click Done")
    banner = None if headless else _Banner(tab, reason, deadline)
    try:
        if banner is not None:
            banner.open()
        while True:
            frame = await _main_frame(tab, deadline)
            if banner is not None and banner.done.is_set():
                return
            if frame is not None:  # None: the page is busy, look again next round
                held = check is not None and await _bounded(
                    check(tab, frame), deadline, reason, timeout
                )
                if held:
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
            # Chrome keeps the fragment apart (urlFragment); the query goes too,
            # or a sign-in page's ?next=/dashboard would pass for the dashboard.
            return url_matches(pattern, frame.get("url", "").split("#", 1)[0].split("?", 1)[0])

        return url_holds
    if callable(until):
        condition = until

        async def holds(tab: Tab, frame: dict) -> bool:
            return bool(await condition(tab))

        return holds
    raise TypeError(f"until must be a URL pattern or an async callable, not {until!r}")


def _call_timeout(deadline: float) -> float:
    """The bound of one CDP call: ``CALL_TIMEOUT``, or what is left before *deadline*."""
    left = deadline - asyncio.get_running_loop().time()
    return min(CALL_TIMEOUT, max(left, MIN_CALL))


def _keep(future: asyncio.Future) -> None:
    """Hold *future* until it ends and read its outcome (no "never retrieved")."""
    _background.add(future)
    future.add_done_callback(_background.discard)
    future.add_done_callback(lambda f: f.cancelled() or f.exception())


async def _headless(tab: Tab, deadline: float = math.inf) -> bool:
    """Whether *tab*'s Chrome is headless: yes if any witness says so.
    :attr:`Browser.headless` knows the flags tellurium launched it with, on
    every platform; Chrome's user agent and product say ``HeadlessChrome``
    when a wrapper script adds the flag, unless ``--user-agent`` rewrites
    them (the new headless mode reports ``Chrome/…`` as product, the old
    shell does not)."""
    if tab._browser.headless:
        return True
    root = tab._browser._router.root
    info = await root.send("Browser.getVersion", {}, timeout=_call_timeout(deadline))
    return any("HeadlessChrome" in info.get(key, "") for key in ("product", "userAgent"))


async def _main_frame(tab: Tab, deadline: float) -> dict | None:
    """The main frame as Chrome reports it; ``None`` if the page is too busy to say."""
    try:
        tree = await tab._session.send("Page.getFrameTree", {}, timeout=_call_timeout(deadline))
    except TimeoutError:
        return None
    return tree["frameTree"]["frame"]


async def _bounded(
    awaitable: Awaitable[bool], deadline: float, reason: str, timeout: float | None
) -> bool:
    """*awaitable*'s result, or the wait's ``TimeoutError`` past *deadline*."""
    left = deadline - asyncio.get_running_loop().time()
    if left == math.inf:
        return await awaitable
    try:
        return await asyncio.wait_for(awaitable, max(left, 0))
    except TimeoutError:
        if asyncio.get_running_loop().time() >= deadline:
            raise _timeout(reason, timeout) from None
        raise


async def _clicked(done: asyncio.Event, seconds: float) -> bool:
    try:
        await asyncio.wait_for(done.wait(), seconds)
    except TimeoutError:
        return False
    return True


def _timeout(reason: str, timeout: float | None) -> TimeoutError:
    within = "" if timeout is None else f" within {timeout:g} s"
    return TimeoutError(f"wait_for_human({reason!r}) did not end{within}")


class _Banner:
    """The banner of one wait: an isolated world per document, the "Done"
    binding in it (a fresh name per wait), and the event that it was clicked."""

    def __init__(self, tab: Tab, reason: str, deadline: float) -> None:
        token = secrets.token_hex(8)
        self._tab = tab
        self._session = tab._session
        self._deadline = deadline
        self._world = f"__tl_human_{token}"
        self._binding = f"__tl_done_{token}"
        self._context: int | None = None
        self._loader: str | None = None  # the document the context belongs to
        self._bound = False
        self._warned: set[str] = set()  # errors of the banner's script, logged once
        # Chrome's reply to the early script (run at every new document): its
        # identifier, needed to take it away.
        self._adding: asyncio.Future | None = None
        self._expression = _SHOW_JS % (
            json.dumps(reason),
            json.dumps(self._binding),
            json.dumps(DONE_LABEL),
        )
        self.done = asyncio.Event()

    def _on_binding(self, params: dict) -> None:
        if params.get("name") == self._binding:
            self.done.set()

    def open(self) -> None:
        """Listen for "Done" and have every new document run the banner's
        script in its world before the page's own scripts.

        A page whose main thread is busy answers late (Chrome replies once
        the page is free): the reply is awaited in the background, never by
        the wait, which a busy page must not shorten nor stretch. It is not
        bounded by a clock but by the tab's session: Chrome fails it when the
        session goes, and the session's early scripts go with it; a reply
        that comes after the wait has the script taken away (:meth:`close`).
        Meanwhile :meth:`show` puts the banner up round by round."""
        self._session.on("Runtime.bindingCalled", self._on_binding)
        self._adding = asyncio.ensure_future(
            self._session.send(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": self._expression, "worldName": self._world},
                timeout=math.inf,
            )
        )
        _keep(self._adding)

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
                # A navigation may have committed meanwhile, so the world and
                # the binding may sit in different documents: keep them only
                # if the document is still the one they were made for.
                now = await _main_frame(self._tab, self._deadline) or {}
                if now.get("loaderId") != frame.get("loaderId"):
                    return
                self._context, self._loader = world["executionContextId"], frame.get("loaderId")
            if await self._evaluate(self._expression) == "unbound":
                self._context = None  # world and binding again next round
        except TimeoutError:
            pass  # a busy page: the same world next round (a new one would show a second banner)
        except (CDPError, KeyError):
            self._context = None  # the document went meanwhile: a new world next round

    async def close(self) -> None:
        """Take the banner out, the binding and the early script away; never
        raises (the tab may be gone). It waits at most ``CALL_TIMEOUT``, or
        ``CLEANUP_GRACE`` once the wait's time is over; the rest, each call
        bounded, goes on in the background, as it does if *close* is cancelled.
        An early script Chrome has not confirmed yet is taken away as soon as
        it does."""
        self._session.off("Runtime.bindingCalled", self._on_binding)
        steps = []
        if self._context is not None:
            steps.append(self._evaluate(_HIDE_JS, CALL_TIMEOUT))
        adding = self._adding
        if adding is not None and adding.done():
            steps.append(self._remove_script(adding))
        elif adding is not None:
            adding.add_done_callback(lambda f: _keep(asyncio.ensure_future(self._remove_script(f))))
        if self._bound:
            steps.append(self._send("Runtime.removeBinding", {"name": self._binding}, CALL_TIMEOUT))
        cleanup = asyncio.ensure_future(asyncio.gather(*steps, return_exceptions=True))
        _keep(cleanup)
        left = self._deadline - asyncio.get_running_loop().time()
        await asyncio.wait({cleanup}, timeout=max(min(CALL_TIMEOUT, left), CLEANUP_GRACE))

    async def _remove_script(self, adding: asyncio.Future) -> None:
        if adding.cancelled() or adding.exception() is not None:
            return  # the tab went: its early scripts with it
        script = adding.result().get("identifier")
        if script is not None:
            params = {"identifier": script}
            await self._send("Page.removeScriptToEvaluateOnNewDocument", params, CALL_TIMEOUT)

    async def _evaluate(self, expression: str, timeout: float | None = None) -> Any:
        params = {"expression": expression, "contextId": self._context, "returnByValue": True}
        resp = await self._send("Runtime.evaluate", params, timeout)
        if details := resp.get("exceptionDetails"):
            error = details.get("exception", {}).get("description") or details.get("text", "?")
            if error not in self._warned:
                self._warned.add(error)
                logger.warning("wait_for_human: the banner could not be shown: %s", error)
        return resp.get("result", {}).get("value")

    async def _send(self, method: str, params: dict, timeout: float | None = None) -> dict:
        limit = _call_timeout(self._deadline) if timeout is None else timeout
        return await self._session.send(method, params, timeout=limit)

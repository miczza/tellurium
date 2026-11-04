"""Browser — launch and manage a Chromium process via CDP pipes."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any

from tellurium.browser.context import BrowserContext, tab_context
from tellurium.browser.cookie_jar import CookieJar
from tellurium.browser.dialog import check_policy
from tellurium.browser.download import Downloads
from tellurium.browser.launch_plan import LaunchPlan
from tellurium.browser.process import BrowserProcess
from tellurium.browser.robots import Robots, close_on_robots
from tellurium.browser.tab import Tab, url_matches
from tellurium.cdp.transport._pipeline import CommandPipeline
from tellurium.cdp.transport._session import SessionRouter
from tellurium.cdp.types import TargetCrashedError

logger = logging.getLogger("tellurium")


class Browser(CookieJar):
    """High-level browser controller: :meth:`launch` (or ``async with
    Browser.launch(...) as browser:``) starts a Chrome talking CDP over pipes.
    """

    def __init__(self) -> None:
        # Populated by launch(); owns process, pipe, profile and forwarder
        self._proc = BrowserProcess()
        self._router: SessionRouter | None = None
        self._dispatch_task: asyncio.Task | None = None
        self._tabs: list[Tab] = []
        self._main_tab: Tab | None = None
        # targetId -> Tab, resolved once an auto-attached page is patched
        self._adopted: dict[str, asyncio.Future] = {}
        self._contexts: dict[str, BrowserContext] = {}
        self._tabs_changed = asyncio.Event()
        self._background: set[asyncio.Future] = set()  # cancelled by close()
        self._user_data_dir: str | None = None
        self._stealth_engine = None
        self._stealth_profile = None
        self._stealth_idle = False
        self._mouse_profile = "normal"
        self._dialogs = "dismiss"  # policy for every tab, see Browser.launch
        self._downloads = Downloads(lambda frame_id: tab_context(self, frame_id))
        self._robots = Robots()  # robots.txt policy and cache, see Browser.launch
        # Manual override applied to every session when stealth is off
        # (with stealth on the StealthEngine already owns the timezone).
        self._timezone_override: str | None = None

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    @classmethod
    async def launch(
        cls,
        *,
        headless: bool = False,
        executable: str | None = None,
        browser: str = "stock",
        user_data_dir: str | None = None,
        args: list[str] | None = None,
        proxy: str | None = None,
        stealth: bool = False,
        stealth_idle: bool = False,
        seed: int | None = None,
        extensions: list[str] | None = None,
        chromium_version: str | None = None,
        chromium_sha256: str | None = None,
        auto_security_update: bool = False,
        webrtc_ip: str | None = None,
        timezone: str | None = None,
        languages: list[str] | None = None,
        viewport: tuple[int, int] | None = None,
        mouse_profile: str = "normal",
        chrome_log: str | Path | None = None,
        dialogs: str = "dismiss",
        downloads_dir: str | Path | None = None,
        respect_robots: bool = False,
        robots_agent: str = "*",
    ) -> Browser:
        """Launch a Chrome process and return a connected :class:`Browser`.

        Parameters
        ----------
        headless:
            Run in headless mode.
        executable:
            Explicit path to Chrome.  When *None* the engine locates one.
        browser:
            ``"stock"`` for normal Chrome, ``"patched"`` for Tellurium's
            fingerprint-resistant Chromium build.
        user_data_dir:
            Chrome profile directory.  A temporary one is created if omitted.
        args:
            Extra CLI flags passed to Chrome (with *stealth*, no ``--user-agent``:
            ``ValueError``, the profile's is the only User-Agent).
        proxy:
            Proxy URL: ``http``, ``https``, ``socks4`` or ``socks5`` (scheme kept).
            With credentials (HTTP/HTTPS only) a local :class:`ProxyForwarder` on
            ``127.0.0.1`` adds them; it wants a secret of its own, which Chrome sends
            through ``Fetch`` on the browser session (one pause per request).
        stealth:
            Enable stealth heuristics (engine-level).
        stealth_idle:
            Fill ``Tab.wait()`` with human-like idle activity (occasional
            low-amplitude mouse micro-movements) instead of sleeping with a
            perfectly still cursor.  Design doc 05 "Idle Simulation".
        seed:
            Fingerprint seed for the patched engine.
        extensions:
            List of paths to unpacked extension directories to load via
            ``--load-extension``.  Each path must be an unpacked directory
            containing ``manifest.json`` (.crx files are not supported).
            Raises :class:`~tellurium.browser.launcher.LaunchError` when
            Chrome branded >= 137 is used (use Chrome for Testing instead).
        timezone:
            Manual IANA timezone override (``"Europe/Rome"``), over GeoIP and
            the stealth profile.  Applied with ``Emulation.setTimezoneOverride``
            even when ``stealth=False``; the patched engine also gets
            ``--fingerprint-timezone``.
        languages:
            Manual ``navigator.languages`` override (``["it-IT", "it", "en"]``).
            Takes precedence over GeoIP / profile.  Passed to Chrome as
            ``--accept-lang`` so the browser derives both ``navigator.languages``
            and the ``Accept-Language`` header natively (a CDP
            ``acceptLanguage`` override leaks the raw q-value string into
            ``navigator.languages``).
        viewport:
            ``(width, height)`` of the browser window, applied as
            ``--window-size=W,H`` at launch.  Headed windows are additionally
            pinned with ``Browser.setWindowBounds`` once the tab exists.
            ``Emulation.setDeviceMetricsOverride`` is deliberately **not** used:
            it desynchronises ``window.outerWidth``/``screen`` from the emulated
            viewport, which is a detection signal.
        mouse_profile:
            Wind-Mouse personality for every ``human=True`` mouse movement:
            ``"careful"``, ``"normal"`` (default) or ``"hasty"`` — see
            ``MOUSE_PROFILES`` in ``tellurium.stealth.human``.
        chrome_log:
            File that receives Chrome's stdout and stderr (appended). By
            default the output is discarded, keeping only its tail to explain
            a failed launch.
        dialogs:
            What every tab does with a JavaScript dialog nobody handles with
            ``Tab.on_dialog``: ``"dismiss"`` (default; ``beforeunload`` is
            accepted), ``"accept"`` or ``"manual"`` (left open).
        downloads_dir:
            Folder that keeps the downloads (named by GUID; ``Download.save_as``
            names them). By default a temporary folder removed by :meth:`close`.
        respect_robots:
            ``Tab.get``, ``new_tab(url)`` and ``get`` raise
            :class:`RobotsDisallowedError` for a URL the site's robots.txt
            disallows, before any request. robots.txt is loaded by Chrome
            (cached 24 h per origin); clicks and redirects are not checked.
        robots_agent:
            Product token whose robots.txt group applies (default ``"*"``).

        Launch is all-or-nothing: on failure or cancellation the process,
        pipe, temporary profile, downloads folder and proxy forwarder are
        released. When Chrome exits during launch, :class:`LaunchError`
        carries its exit code and last output (e.g. a profile already in use).
        """
        from tellurium.stealth.human import MOUSE_PROFILES

        if mouse_profile not in MOUSE_PROFILES:
            raise ValueError(
                f"Unknown mouse_profile {mouse_profile!r}; expected one of {sorted(MOUSE_PROFILES)}"
            )
        plan = LaunchPlan(
            headless=headless,
            executable=executable,
            browser=browser,
            user_data_dir=user_data_dir,
            args=args,
            proxy=proxy,
            stealth=stealth,
            seed=seed,
            extensions=extensions,
            chromium_version=chromium_version,
            chromium_sha256=chromium_sha256,
            auto_security_update=auto_security_update,
            webrtc_ip=webrtc_ip,
            timezone=timezone,
            languages=languages,
            viewport=viewport,
        )

        self = cls()
        self._dialogs = check_policy(dialogs)
        self._robots = Robots(respect_robots, robots_agent)
        self._stealth_idle = stealth_idle
        self._mouse_profile = mouse_profile
        try:
            # 1-8. Engine, executable, forwarder, profile, stealth profile, flags
            await plan.compose(self._proc)
            self._engine = plan.engine
            self._user_data_dir = plan.profile_dir
            stealth_engine = self._stealth_engine = plan.stealth_engine
            self._stealth_profile = plan.stealth_profile
            downloads = downloads_dir or self._proc.make_downloads_dir()

            # 9-10. Launch Chrome, route sessions, answer the forwarder's 407 (proxy auth)
            transport = await self._proc.spawn(plan.chrome_path, plan.flags, chrome_log)
            self._router = SessionRouter(transport)
            self._dispatch_task = asyncio.create_task(self._router.run())
            self._proc.reader = self._dispatch_task
            await self._proc.answer_proxy_auth(self._router.root)
            await self._downloads.start(
                self._router.root, downloads, downloads_dir is None, self._dispatch_task
            )

            # 11. Wire stealth engine to router; align its profile with the
            # running binary (real version, GREASE brand, WebRTC IP).
            if stealth_engine is not None:
                stealth_engine.set_router(self._router)
                await plan.align_stealth(self._router.root)
                self._stealth_profile = plan.stealth_profile

            # 12. Discover initial page target
            await self._router.root.send("Target.setDiscoverTargets", {"discover": True})
            targets_result = await self._router.root.send("Target.getTargets", {})
            infos = targets_result.get("targetInfos", [])
            page_target = next((t for t in infos if t.get("type") == "page"), None)

            if page_target:
                session = await self._router.attach(page_target["targetId"])
                # Without Page.enable no javascriptDialogOpening is reported,
                # so a dialog opened before the first get() would stay open.
                await session.send("Page.enable", {}, timeout=10)
                tab = Tab(
                    session,
                    self,
                    page_target["targetId"],
                    stealth_idle=stealth_idle,
                    mouse_profile=mouse_profile,
                    dialogs=self._dialogs,
                )
                tab._url = page_target.get("url", "")
                self._tabs.append(tab)
                self._main_tab = tab

                # 12a. Manual timezone override without stealth: the StealthEngine
                # is not there to send it, so do it here (design doc 01 §Override).
                if timezone is not None and stealth_engine is None:
                    self._timezone_override = timezone
                    await self._apply_manual_overrides(session)

                # 13. Apply stealth to initial tab session
                if stealth_engine is not None:
                    await stealth_engine.apply_to_session(session)
                    # T7: inject runtime stealth scripts before any navigation, so
                    # stealth=True works on Chrome branded >=137 where
                    # --load-extension is silently rejected.
                    await stealth_engine.apply_page_scripts(session)

            # 14. Setup auto-attach for OOPIF / worker CDP patching (T7, T7.7).
            # _STEALTH_TARGET_FILTER excludes 'page', so explicit attachToTarget
            # from new_tab() is unaffected. Iframes/workers trigger the listener
            # which routes to _on_target_attached -> _patch_and_resume.
            #
            # T7.7: auto-attach must be armed on the *page* session too — a
            # browser-root-only setAutoAttach never fires for a page's OOPIFs or
            # dedicated workers (verified empirically on Chrome 153). The root
            # wiring stays for browser-scoped service workers.
            #
            # The root auto-attach also covers every *new page* (popups, new_tab,
            # context tabs): each one is frozen until _adopt_page has patched it.
            root = self._router.root
            root.on("Target.attachedToTarget", self._on_attached_to_target)
            root.on("Target.targetInfoChanged", self._on_target_info_changed)
            root.on("Target.targetDestroyed", self._on_target_destroyed)
            root.on("Target.targetCrashed", self._on_target_crashed)
            if stealth_engine is not None:
                await stealth_engine.wire_session(root, include_pages=True)
                if self._main_tab is not None:
                    await stealth_engine.wire_session(self._main_tab._session)
            else:
                await root.send(
                    "Target.setAutoAttach",
                    {
                        "autoAttach": True,
                        "waitForDebuggerOnStart": True,
                        "flatten": True,
                        "filter": [{"type": "page", "exclude": False}],
                    },
                )

            # 15. Pin the window geometry for a headed browser. --window-size is
            # honoured at startup by headless Chrome but a window manager can
            # ignore/adjust it for a real window, so re-assert it over CDP.
            if viewport is not None and not headless and self._main_tab is not None:
                try:
                    await self._main_tab.set_viewport(int(viewport[0]), int(viewport[1]))
                except Exception as exc:  # noqa: BLE001 — cosmetic, never fatal
                    logger.warning("Could not apply viewport %r: %s", viewport, exc)

        except BaseException as exc:
            self._stealth_engine = plan.stealth_engine  # built before the failure
            error = await self._abort_launch(exc)
            if error is not None:
                raise error from exc
            raise
        return self

    async def _abort_launch(self, cause: BaseException) -> Exception | None:
        try:
            return await self._proc.launch_error(cause)
        finally:
            await self.close()  # runs every step even if cancelled again

    async def _apply_manual_overrides(self, session: Any) -> None:
        """Apply non-stealth manual overrides to a freshly attached session."""
        if self._timezone_override is None:
            return
        try:
            await session.send(
                "Emulation.setTimezoneOverride", {"timezoneId": self._timezone_override}
            )
        except Exception as exc:  # noqa: BLE001 — a bad IANA id must not kill launch
            logger.warning(
                "Timezone override %r rejected by Chrome: %s", self._timezone_override, exc
            )

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    async def new_tab(self, url: str = "about:blank") -> Tab:
        """Open a new tab, navigate to *url*, wait for load, and return it."""
        result = await self._router.root.send("Target.createTarget", {"url": "about:blank"})
        tab = await self._wait_adopted(result["targetId"])
        if url and url != "about:blank":
            await close_on_robots(tab, tab.get(url))
        return tab

    @property
    def tabs(self) -> list[Tab]:
        return list(self._tabs)

    @property
    def downloads(self) -> Downloads:  # internal: Tab.expect_download, contexts
        return self._downloads

    @property
    def headless(self) -> bool:
        """Whether Chrome was launched headless (read-only): from the flags it got,
        ``headless=True`` or ``--headless`` in ``args``, on every platform."""
        return self._proc.headless

    async def wait_for_tab(self, url: str, *, timeout: float = 30) -> Tab:
        """Return the first open tab whose URL matches *url*, waiting for one.

        Meant for popups (``target=_blank`` links, ``window.open``): they are
        tracked automatically and show up in :attr:`tabs`. *url* is a glob
        when it contains ``*`` or ``?``, a substring otherwise.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            for tab in self._tabs:
                if url_matches(url, tab.url):
                    return tab
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for a tab matching {url!r}")
            self._tabs_changed.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._tabs_changed.wait(), timeout=remaining)

    # ------------------------------------------------------------------
    # Page target tracking
    # ------------------------------------------------------------------

    def _find_tab(self, target_id: str) -> Tab | None:
        return next((t for t in self._tabs if t._target_id == target_id), None)

    def _on_attached_to_target(self, params: dict) -> None:
        info = params.get("targetInfo", {})
        if info.get("type") != "page":
            return
        session = self._router.register(params["sessionId"])
        waiting = bool(params.get("waitingForDebugger"))
        loop = asyncio.get_running_loop()
        if self._find_tab(info["targetId"]) is not None:
            # Already driven through its own session (the initial tab).
            loop.create_task(self._release_duplicate(session, waiting))
        else:
            loop.create_task(self._adopt_page(session, info, waiting))

    async def _release_duplicate(self, session: Any, waiting: bool) -> None:
        try:
            if waiting:
                await session.send("Runtime.runIfWaitingForDebugger", {})
            await self._router.detach(session)
        except Exception:  # noqa: BLE001 — target may be gone already
            logger.debug("Could not release duplicate page session", exc_info=True)

    async def _adopt_page(self, session: Any, info: dict, waiting: bool) -> None:
        """Track a new page and patch it before it runs a single script."""
        target_id = info["targetId"]
        adopted = self._adopted.setdefault(target_id, asyncio.get_running_loop().create_future())
        tab = Tab(
            session,
            self,
            target_id,
            stealth_idle=self._stealth_idle,
            mouse_profile=self._mouse_profile,
            dialogs=self._dialogs,
        )
        tab._url = info.get("url", "")
        self._tabs.append(tab)
        context = self._contexts.get(info.get("browserContextId", ""))
        if context is not None:
            context._tabs.append(tab)
        # A frozen popup answers nothing until it is resumed, so the patches
        # are pipelined ahead of the resume instead of awaited one by one:
        # the target processes them in order, before its first script.
        pipeline = CommandPipeline(session)
        try:
            await self._prepare_page_session(pipeline)
        except Exception:  # noqa: BLE001 — never leave the page frozen
            logger.warning("Could not prepare new tab %s", target_id, exc_info=True)
        if waiting:
            await pipeline.send("Runtime.runIfWaitingForDebugger", {})
        await pipeline.drain(target_id)
        if not adopted.done():
            adopted.set_result(tab)
        self._tabs_changed.set()

    async def _prepare_page_session(self, session: Any) -> None:
        # Page.enable first: without it scripts registered on a frozen page
        # are not run at document-start (same as for OOPIFs, T7.7).
        await session.send("Page.enable", {})
        if self._stealth_engine is not None:
            await self._stealth_engine.apply_to_session(session)
            await self._stealth_engine.apply_page_scripts(session)
            # T7.7: OOPIF/worker auto-attach is per-page-session.
            await self._stealth_engine.wire_session(session)
        else:
            await self._apply_manual_overrides(session)

    async def _wait_adopted(self, target_id: str, timeout: float = 10) -> Tab:
        adopted = self._adopted.setdefault(target_id, asyncio.get_running_loop().create_future())
        try:
            return await asyncio.wait_for(asyncio.shield(adopted), timeout=timeout)
        except TimeoutError:
            raise TimeoutError(f"New tab {target_id} was not ready within {timeout}s") from None

    def _on_target_info_changed(self, params: dict) -> None:
        info = params.get("targetInfo", {})
        tab = self._find_tab(info.get("targetId", ""))
        if tab is not None and info.get("url"):
            tab._url = info["url"]
            self._tabs_changed.set()

    def _on_target_destroyed(self, params: dict) -> None:
        self._forget_tab(params.get("targetId", ""))

    def _on_target_crashed(self, params: dict) -> None:
        # Reported to every client with target discovery on. Without it a
        # crashed renderer leaves each command on the tab waiting forever.
        tab = self._find_tab(params.get("targetId", ""))
        if tab is not None:
            reason = f"Renderer crashed ({params.get('status', 'unknown')}): {tab._target_id}"
            tab._session._close(reason, TargetCrashedError)
            self._forget_tab(tab._target_id)
            # The dead tab stays open in Chrome (memory, a page in getTargets).
            task = asyncio.get_running_loop().create_task(self._discard_target(tab._target_id))
            self._background.add(task)
            task.add_done_callback(self._background.discard)

    async def _discard_target(self, target_id: str) -> None:
        try:
            await self._router.root.send("Target.closeTarget", {"targetId": target_id}, timeout=5)
        except Exception:  # noqa: BLE001 — already gone, or the browser is closing
            logger.debug("Could not close crashed target %s", target_id, exc_info=True)

    async def _close_tab(self, tab: Tab, timeout: float = 5) -> None:
        """Close *tab* and wait until Chrome reports its target destroyed."""
        await self._router.root.send("Target.closeTarget", {"targetId": tab._target_id})
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not tab._closed and loop.time() < deadline:
            self._tabs_changed.clear()
            try:
                await asyncio.wait_for(self._tabs_changed.wait(), timeout=deadline - loop.time())
            except TimeoutError:
                break
        self._forget_tab(tab._target_id)

    def _forget_tab(self, target_id: str) -> None:
        self._adopted.pop(target_id, None)
        tab = self._find_tab(target_id)
        if tab is None:
            return
        tab._closed = True
        self._tabs.remove(tab)
        if tab is self._main_tab:  # never leave main_tab on a dead tab
            self._main_tab = self._tabs[0] if self._tabs else None
        for context in self._contexts.values():
            if tab in context._tabs:
                context._tabs.remove(tab)
        self._tabs_changed.set()

    @property
    def main_tab(self) -> Tab:
        if self._main_tab is None:
            raise RuntimeError("No main tab — browser may not be launched")
        return self._main_tab

    async def get(self, url: str, **kwargs: Any) -> Tab:
        """Navigate the main tab (a new one if all closed or crashed) to *url*; return it."""
        if self._main_tab is None:
            self._main_tab = await self.new_tab("about:blank")
        tab = self._main_tab
        await tab.get(url, **kwargs)
        return tab

    # ------------------------------------------------------------------
    # Contexts
    # ------------------------------------------------------------------

    async def new_context(
        self, proxy: str | None = None, downloads_dir: str | Path | None = None
    ) -> BrowserContext:
        """Create an isolated browser context (like incognito); see
        :meth:`BrowserContext.create` for its downloads folder."""
        return await BrowserContext.create(self, proxy, downloads_dir)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Terminate the browser and release every resource, even if this call is
        cancelled meanwhile (the cancellation is re-raised afterwards)."""
        self._robots.close()  # downloads of robots.txt in flight
        try:  # unfinished downloads first: Chrome then deletes their partial files
            await self._downloads.stop("The browser closed")
        finally:
            try:
                await self._proc.close()
            finally:  # the stealth extension's temp dir, now rather than at GC
                if self._stealth_engine is not None:
                    self._stealth_engine.close()
                for task in list(self._background):  # late replies Chrome will never send
                    task.cancel()

    async def __aenter__(self) -> Browser:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

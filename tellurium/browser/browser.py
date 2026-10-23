"""Browser — launch and manage a Chromium process via CDP pipes."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from pathlib import Path
from typing import Any

from tellurium.browser.context import BrowserContext
from tellurium.browser.cookie import Cookie, clear_jar, read_jar
from tellurium.browser.dialog import check_policy
from tellurium.browser.engine import PatchedEngine, StockEngine
from tellurium.browser.launcher import (
    _detect_chrome_version,
    build_chrome_flags,
    build_load_extension_flag,
    check_chrome_version_for_extensions,
    validate_extension_paths,
)
from tellurium.browser.process import BrowserProcess
from tellurium.browser.proxy import forwarder_for, proxy_server_flag
from tellurium.browser.tab import Tab, url_matches
from tellurium.cdp.transport._pipeline import CommandPipeline
from tellurium.cdp.transport._session import SessionRouter
from tellurium.cdp.types import TargetCrashedError
from tellurium.stealth._grease import parse_grease_brands, parse_product_version
from tellurium.stealth._webrtc import resolve_webrtc_ip

logger = logging.getLogger("tellurium")


class Browser:
    """High-level browser controller.

    Use :meth:`launch` (or ``async with Browser.launch(...) as browser:``) to
    create an instance backed by a real Chrome/Chromium process communicating
    over CDP pipes.
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
        self._background: set[asyncio.Task] = set()
        self._user_data_dir: str | None = None
        self._stealth_engine = None
        self._stealth_profile = None
        self._stealth_idle = False
        self._mouse_profile = "normal"
        self._dialogs = "dismiss"  # policy for every tab, see Browser.launch
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
            Extra CLI flags passed to Chrome.
        proxy:
            Proxy URL: ``http``, ``https``, ``socks4`` or ``socks5`` (scheme
            kept for Chrome). With credentials (HTTP/HTTPS only) a local
            :class:`ProxyForwarder` adds them, so Chrome only sees
            ``127.0.0.1:<port>``.
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
            Manual IANA timezone override (``"Europe/Rome"``).  Takes
            precedence over the GeoIP result and over the stealth profile's
            default.  Applied with ``Emulation.setTimezoneOverride`` even when
            ``stealth=False``.
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

        Launch is all-or-nothing: on failure or cancellation the process,
        pipe, temporary profile and proxy forwarder are released. When
        Chrome exits during launch, :class:`LaunchError` carries its exit
        code and last output (e.g. a profile already in use).
        """
        from tellurium.stealth.human import MOUSE_PROFILES

        if mouse_profile not in MOUSE_PROFILES:
            raise ValueError(
                f"Unknown mouse_profile {mouse_profile!r}; expected one of {sorted(MOUSE_PROFILES)}"
            )
        if languages is not None and (not isinstance(languages, (list, tuple)) or not languages):
            raise ValueError("languages must be a non-empty list, e.g. ['it-IT', 'it']")
        if viewport is not None:
            if len(tuple(viewport)) != 2:
                raise ValueError("viewport must be a (width, height) tuple")
            if int(viewport[0]) <= 0 or int(viewport[1]) <= 0:
                raise ValueError("viewport width and height must be positive")

        self = cls()
        self._dialogs = check_policy(dialogs)
        self._stealth_idle = stealth_idle
        self._mouse_profile = mouse_profile
        languages = list(languages) if languages is not None else None

        # 0. Validate extension paths up-front (before any async work)
        validate_extension_paths(extensions or [])

        # 0b. Resolve webrtc_ip up-front: the native patch only understands an
        # IP literal (or its own 'disable', which drops every candidate), so
        # 'auto' must reach it already resolved and our 'disable' — no
        # spoofing — must leave the flag out entirely.
        if webrtc_ip is not None:
            resolved_webrtc_ip = resolve_webrtc_ip(webrtc_ip, proxy=proxy)
        else:
            resolved_webrtc_ip = None

        # 1. Select engine
        if browser == "patched":
            engine = PatchedEngine(
                executable=executable,
                chromium_version=chromium_version,
                chromium_sha256=chromium_sha256,
                auto_security_update=auto_security_update,
                webrtc_ip_flag=resolved_webrtc_ip,
            )
        else:
            if chromium_version or chromium_sha256 or auto_security_update:
                logger.warning(
                    "chromium_version/chromium_sha256/auto_security_update are only "
                    "meaningful with browser='patched'; ignoring for browser=%r.",
                    browser,
                )
            engine = StockEngine(executable=executable)
        self._engine = engine

        # 2. Get executable
        chrome_path = await engine.get_executable()

        # 2a. Chrome 137+ branded check for extensions
        if extensions:
            version = await asyncio.to_thread(_detect_chrome_version, chrome_path)
            p = chrome_path.lower()
            is_branded_chrome = (
                "google-chrome" in p  # linux binary name
                or p.endswith("google chrome")  # macOS .app bundle
                or "\\google\\chrome\\" in p  # Windows install path
                or "/google/chrome/" in p  # normalized Windows path
            )
            check_chrome_version_for_extensions(
                executable=chrome_path,
                version=version,
                is_branded_chrome=is_branded_chrome,
                extensions=extensions,
            )
            if os.environ.get("TELLURIUM_SUPPRESS_EXTENSION_WARNING") != "1":
                logger.warning(
                    "User extensions loaded: %s. "
                    "Extensions expose 4 fingerprint vectors: "
                    "(1) chrome.runtime.sendMessage enumeration, "
                    "(2) DOM signatures (injected elements/stylesheets), "
                    "(3) Window globals (e.g. window.__extension_*), "
                    "(4) web_accessible_resources probing via chrome-extension://<id>/.",
                    ", ".join(extensions),
                )

        # Validated before any resource exists (scheme, SOCKS credentials).
        forwarder = forwarder_for(proxy) if proxy else None
        proxy_flag = proxy_server_flag(proxy) if proxy else None
        try:
            # 3. Proxy with auth -> start forwarder
            if forwarder is not None:
                await self._proc.start_forwarder(forwarder)
                proxy_flag = f"http://127.0.0.1:{forwarder.port}"

            # 4. User-data dir
            self._user_data_dir = user_data_dir or self._proc.make_temp_profile()

            # 5. Build stealth profile & engine (if stealth=True)
            stealth_engine = None
            stealth_profile = None

            if stealth:
                from tellurium.stealth.engine import StealthEngine
                from tellurium.stealth.profile import StealthProfile

                # Build profile
                if seed is not None:
                    stealth_profile = StealthProfile.from_seed(seed)
                else:
                    stealth_profile = StealthProfile.auto()

                # GeoIP resolution if proxy — resolve real exit IP
                if proxy:
                    try:
                        from tellurium.stealth.geoip import resolve_exit_ip, resolve_geoip

                        forwarder_port = self._proc.forwarder.port if self._proc.forwarder else None
                        exit_ip = resolve_exit_ip(proxy, forwarder_port)
                        logger.info("Proxy exit IP: %s", exit_ip)
                        geo = resolve_geoip(exit_ip)
                        stealth_profile = dataclasses.replace(
                            stealth_profile,
                            languages=geo.languages,
                            timezone=geo.timezone,
                            locale=geo.languages[0],
                            accept_language=", ".join(
                                f"{lang};q={1.0 - i * 0.1:.1f}" if i > 0 else lang
                                for i, lang in enumerate(geo.languages)
                            ),
                        )
                    except Exception as e:  # noqa: BLE001 - GeoIP is best-effort
                        logger.warning("GeoIP not available: %s. Using default locale.", e)

                # Manual overrides win over both GeoIP and the seeded defaults
                # (design doc 01 §"Override manuali (ignorano auto-detect)").
                manual: dict[str, Any] = {}
                if timezone is not None:
                    manual["timezone"] = timezone
                if languages is not None:
                    from tellurium.stealth.profile import build_accept_language

                    manual["languages"] = languages
                    manual["locale"] = languages[0]
                    manual["accept_language"] = build_accept_language(languages)
                if manual:
                    stealth_profile = dataclasses.replace(stealth_profile, **manual)

                stealth_engine = StealthEngine(
                    engine,
                    stealth_profile,
                    headless,
                    proxy is not None,
                )
                self._stealth_engine = stealth_engine
                self._stealth_profile = stealth_profile

            # 6. Build engine-specific args
            if stealth and stealth_profile is not None:
                engine_args = engine.build_args(stealth_profile)
            else:
                profile_obj = None
                if seed is not None:

                    class _P:
                        pass

                    profile_obj = _P()
                    profile_obj.seed = seed  # type: ignore[attr-defined]
                engine_args = engine.build_args(profile_obj)

            # 7. Stealth flags (extension + WebRTC)
            stealth_flags: list[str] = []
            user_exts: list[str] = extensions or []

            # Languages: let Chrome derive both navigator.languages and the
            # Accept-Language header (with its native q-values) from the
            # --accept-lang pref. Overriding acceptLanguage via
            # Emulation.setUserAgentOverride leaks the raw string into
            # navigator.languages (["en-US", "en;q=0.9"]) and produces a
            # malformed header ("en-US, en;q=0.9;q=0.9"). Measured on Chrome 153.
            # The same flag carries a manual languages= override with stealth off.
            effective_languages = languages
            if effective_languages is None and stealth and stealth_profile is not None:
                effective_languages = stealth_profile.languages
            if effective_languages:
                stealth_flags.append("--accept-lang=" + ",".join(effective_languages))

            if viewport is not None:
                stealth_flags.append(f"--window-size={int(viewport[0])},{int(viewport[1])}")

            if stealth and stealth_engine is not None:
                ext_path = stealth_engine.build_extension()
                if ext_path or user_exts:
                    stealth_flags.append(
                        build_load_extension_flag(
                            tellurium_stealth_path=ext_path,
                            user_extensions=user_exts,
                        )
                    )
                # Note: --disable-blink-features=AutomationControlled is
                # intentionally NOT added. Chrome shows an "unsupported
                # command-line flag" warning bar when it is present, which is
                # itself a detection signal. The stealth extension's
                # webdriver.js overrides navigator.webdriver via JS injection
                # because --remote-debugging-pipe makes the native value true.
                if proxy:
                    stealth_flags.append(
                        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"
                    )
            elif user_exts:
                # stealth=False but user extensions still need to be loaded
                stealth_flags.append(
                    build_load_extension_flag(
                        tellurium_stealth_path=None,
                        user_extensions=user_exts,
                    )
                )

            # 8. Build flags
            flags = build_chrome_flags(
                headless=headless,
                user_data_dir=self._user_data_dir,
                proxy=proxy_flag,
                extra_args=(args or []) + stealth_flags,
                engine_args=engine_args,
            )

            # 9-10. Launch Chrome, connect its pipe, route sessions
            transport = await self._proc.spawn(chrome_path, flags, chrome_log)
            self._router = SessionRouter(transport)
            self._dispatch_task = asyncio.create_task(self._router.run())
            self._proc.reader = self._dispatch_task

            # 11. Wire stealth engine to router
            if stealth_engine is not None:
                stealth_engine.set_router(self._router)

            # 11a. review 2026-04-15 #5/#9: read the real GREASE brand from the browser
            # and coalesce with webrtc_public_ip into a single dataclasses.replace() call.
            if stealth and stealth_engine is not None and stealth_profile is not None:
                try:
                    version_info = await self._router.root.send(
                        "Browser.getVersion", {}, timeout=5.0
                    )
                except Exception:  # noqa: BLE001 - best-effort version probe
                    version_info = {}
                raw_brands = version_info.get("userAgentData", {}).get("brands") or []
                # Build a single replace() call for both GREASE and webrtc fields
                replace_kwargs: dict = {}
                # Align UA / Client Hints with the version the binary really has
                # ("Chrome/153.0.8010.36", "HeadlessChrome/..."): the profile's
                # default browser_version is only a fallback.
                real_version = parse_product_version(version_info.get("product", ""))
                if real_version and real_version != stealth_profile.browser_version:
                    stealth_profile = stealth_profile.with_browser_version(real_version)
                if raw_brands:
                    g_brand, g_version = parse_grease_brands(raw_brands)
                    replace_kwargs["grease_brand"] = g_brand
                    replace_kwargs["grease_version"] = g_version
                if resolved_webrtc_ip is not None:
                    replace_kwargs["webrtc_public_ip"] = resolved_webrtc_ip
                if replace_kwargs:
                    stealth_profile = dataclasses.replace(stealth_profile, **replace_kwargs)
                if stealth_profile is not self._stealth_profile:
                    stealth_engine.update_profile(stealth_profile)
                    self._stealth_profile = stealth_profile
                # else: leave profile.grease_brand = None → engine falls back to "Not_A Brand"/"24"
                #       and webrtc_public_ip = None → webrtc.js no-op

            # 12. Discover initial page target
            await self._router.root.send("Target.setDiscoverTargets", {"discover": True})
            targets_result = await self._router.root.send("Target.getTargets", {})
            page_target = None
            for t in targets_result.get("targetInfos", []):
                if t.get("type") == "page":
                    page_target = t
                    break

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
                "Emulation.setTimezoneOverride",
                {
                    "timezoneId": self._timezone_override,
                },
            )
        except Exception as exc:  # noqa: BLE001 — a bad IANA id must not kill launch
            logger.warning(
                "Timezone override %r rejected by Chrome: %s",
                self._timezone_override,
                exc,
            )

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    async def new_tab(self, url: str = "about:blank") -> Tab:
        """Open a new tab, navigate to *url*, wait for load, and return it."""
        result = await self._router.root.send("Target.createTarget", {"url": "about:blank"})
        tab = await self._wait_adopted(result["targetId"])
        if url and url != "about:blank":
            await tab.get(url)
        return tab

    @property
    def tabs(self) -> list[Tab]:
        return list(self._tabs)

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
            try:
                await asyncio.wait_for(self._tabs_changed.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                pass

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
        except asyncio.TimeoutError:  # not the builtin TimeoutError on Python 3.10
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
            except asyncio.TimeoutError:
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
        """Navigate the main tab to *url* and return it.

        Opens a new main tab when there is none (all closed or crashed).
        """
        if self._main_tab is None:
            self._main_tab = await self.new_tab("about:blank")
        tab = self._main_tab
        await tab.get(url, **kwargs)
        return tab

    # ------------------------------------------------------------------
    # Cookies
    # ------------------------------------------------------------------

    async def get_cookies(self, domain: str | None = None) -> list[Cookie]:
        """Browser cookies; with *domain*, only its own and its subdomains'."""
        return await read_jar(self._router.root, domain)

    async def set_cookies(self, cookies: list[Cookie]) -> None:
        """Set cookies in the browser."""
        await self._router.root.send(
            "Storage.setCookies", {"cookies": [c.to_json() for c in cookies]}
        )

    async def clear_cookies(self, domain: str | None = None) -> None:
        """Delete every cookie, or only *domain*'s (and its subdomains')."""
        await clear_jar(self._router.root, domain)

    async def save_cookies(
        self, path: str, format: str = "json", domain: str | None = None
    ) -> None:
        """Save cookies to *path* in the given format."""
        cookies = await self.get_cookies(domain)
        await asyncio.to_thread(Cookie.save_list, cookies, path, format=format)

    async def load_cookies(self, path: str, format: str | None = None) -> None:
        """Load cookies from *path* and set them in the browser."""
        await self.set_cookies(await asyncio.to_thread(Cookie.load_list, path, format=format))

    # ------------------------------------------------------------------
    # Contexts
    # ------------------------------------------------------------------

    async def new_context(self, proxy: str | None = None) -> BrowserContext:
        """Create an isolated browser context (like incognito)."""
        params: dict[str, Any] = {}
        if proxy:
            params["proxyServer"] = proxy
        result = await self._router.root.send("Target.createBrowserContext", params)
        context = BrowserContext(self, result["browserContextId"])
        self._contexts[context.context_id] = context
        return context

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Terminate the browser process and clean up resources.

        Every resource is released even if this call is cancelled meanwhile;
        the cancellation is re-raised afterwards.
        """
        await self._proc.close()

    async def __aenter__(self) -> Browser:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

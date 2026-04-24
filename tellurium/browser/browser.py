"""Browser — launch and manage a Chromium process via CDP pipes."""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import shutil
import signal
import tempfile
from pathlib import Path
from typing import Any

from tellurium.browser.cookie import Cookie
from tellurium.browser.context import BrowserContext
from tellurium.browser.engine import StockEngine, PatchedEngine
from tellurium.stealth._grease import parse_grease_brands
from tellurium.stealth._webrtc import resolve_webrtc_ip
from tellurium.browser.launcher import (
    _detect_chrome_version,
    build_chrome_flags,
    build_load_extension_flag,
    check_chrome_version_for_extensions,
    launch_chrome_posix,
    validate_extension_paths,
)
from tellurium.browser.proxy import ProxyForwarder, parse_proxy_url
from tellurium.browser.tab import Tab
from tellurium.cdp.transport import create_transport
from tellurium.cdp.transport._session import SessionRouter

logger = logging.getLogger("tellurium")


class Browser:
    """High-level browser controller.

    Use :meth:`launch` (or ``async with Browser.launch(...) as browser:``) to
    create an instance backed by a real Chrome/Chromium process communicating
    over CDP pipes.
    """

    def __init__(self) -> None:
        # Populated by launch()
        self._process = None
        self._router: SessionRouter | None = None
        self._dispatch_task: asyncio.Task | None = None
        self._tabs: list[Tab] = []
        self._main_tab: Tab | None = None
        self._tmp_dir: str | None = None
        self._forwarder: ProxyForwarder | None = None
        self._user_data_dir: str | None = None
        self._stealth_engine = None
        self._stealth_profile = None

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
        seed: int | None = None,
        extensions: list[str] | None = None,
        chromium_version: str | None = None,
        chromium_sha256: str | None = None,
        auto_security_update: bool = False,
        webrtc_ip: str | None = None,
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
            Proxy URL, e.g. ``"http://user:pass@host:port"``.  If the URL
            contains credentials a local :class:`ProxyForwarder` is started
            automatically so Chrome only sees ``localhost:<port>``.
        stealth:
            Enable stealth heuristics (engine-level).
        seed:
            Fingerprint seed for the patched engine.
        extensions:
            List of paths to unpacked extension directories to load via
            ``--load-extension``.  Each path must be an unpacked directory
            containing ``manifest.json`` (.crx files are not supported).
            Raises :class:`~tellurium.browser.launcher.LaunchError` when
            Chrome branded >= 137 is used (use Chrome for Testing instead).
        """
        self = cls()

        # 0. Validate extension paths up-front (before any async work)
        validate_extension_paths(extensions or [])

        # 1. Select engine
        if browser == "patched":
            engine = PatchedEngine(
                executable=executable,
                chromium_version=chromium_version,
                chromium_sha256=chromium_sha256,
                auto_security_update=auto_security_update,
                webrtc_ip_flag=webrtc_ip,  # raw user setting; native patch accepts ip/auto/disable
            )
        else:
            if chromium_version or chromium_sha256 or auto_security_update:
                logger.warning(
                    "chromium_version/chromium_sha256/auto_security_update are only "
                    "meaningful with browser='patched'; ignoring for browser=%r.", browser
                )
            engine = StockEngine(executable=executable)
        self._engine = engine

        # 2. Get executable
        chrome_path = await engine.get_executable()

        # 2a. Chrome 137+ branded check for extensions
        if extensions:
            version = _detect_chrome_version(chrome_path)
            p = chrome_path.lower()
            is_branded_chrome = (
                "google-chrome" in p                        # linux binary name
                or p.endswith("google chrome")              # macOS .app bundle
                or "\\google\\chrome\\" in p               # Windows install path
                or "/google/chrome/" in p                  # normalized Windows path
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

        # 3. Proxy with auth -> start forwarder
        proxy_flag: str | None = None
        if proxy:
            info = parse_proxy_url(proxy)
            if info["username"] and info["password"]:
                self._forwarder = ProxyForwarder(
                    info["host"], info["port"], info["username"], info["password"],
                )
                await self._forwarder.start()
                proxy_flag = f"localhost:{self._forwarder.port}"
            else:
                proxy_flag = f"{info['host']}:{info['port']}"

        # 3b. Resolve webrtc_ip setting (after proxy is known)
        if webrtc_ip is not None:
            resolved_webrtc_ip = resolve_webrtc_ip(webrtc_ip, proxy=proxy)
        else:
            resolved_webrtc_ip = None

        # 4. User-data dir
        if user_data_dir:
            self._user_data_dir = user_data_dir
        else:
            self._tmp_dir = tempfile.mkdtemp(prefix="tellurium_")
            self._user_data_dir = self._tmp_dir

        # 5. Build stealth profile & engine (if stealth=True)
        stealth_engine = None
        stealth_profile = None

        if stealth:
            from tellurium.stealth.profile import StealthProfile
            from tellurium.stealth.engine import StealthEngine

            # Build profile
            if seed is not None:
                stealth_profile = StealthProfile.from_seed(seed)
            else:
                stealth_profile = StealthProfile.auto()

            # GeoIP resolution if proxy — resolve real exit IP
            if proxy:
                try:
                    from tellurium.stealth.geoip import resolve_exit_ip, resolve_geoip

                    forwarder_port = self._forwarder.port if self._forwarder else None
                    exit_ip = resolve_exit_ip(proxy, forwarder_port)
                    logger.info("Proxy exit IP: %s", exit_ip)
                    geo = resolve_geoip(exit_ip)
                    stealth_profile = dataclasses.replace(
                        stealth_profile,
                        languages=geo.languages,
                        timezone=geo.timezone,
                        locale=geo.languages[0],
                        accept_language=", ".join(
                            f"{l};q={1.0 - i * 0.1:.1f}" if i > 0 else l
                            for i, l in enumerate(geo.languages)
                        ),
                    )
                except (ImportError, Exception) as e:
                    logger.warning("GeoIP not available: %s. Using default locale.", e)

            stealth_engine = StealthEngine(
                engine, stealth_profile, headless, proxy is not None,
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
            # webdriver.js already overrides navigator.webdriver.
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

        # 9. Launch Chrome
        process, write_fd, read_fd = launch_chrome_posix(chrome_path, flags)
        self._process = process

        # 10. Transport + router
        transport = create_transport(read_fd, write_fd)
        await transport.start()
        self._router = SessionRouter(transport)
        self._dispatch_task = asyncio.create_task(self._router.run())

        # 11. Wire stealth engine to router
        if stealth_engine is not None:
            stealth_engine.set_router(self._router)

        # 11a. review 2026-04-15 #5/#9: read the real GREASE brand from the browser
        # and coalesce with webrtc_public_ip into a single dataclasses.replace() call.
        if stealth and stealth_engine is not None and stealth_profile is not None:
            try:
                version_info = await self._router.root.send("Browser.getVersion", {}, timeout=5.0)
            except Exception:
                version_info = {}
            raw_brands = version_info.get("userAgentData", {}).get("brands") or []
            # Build a single replace() call for both GREASE and webrtc fields
            replace_kwargs: dict = {}
            if raw_brands:
                g_brand, g_version = parse_grease_brands(raw_brands)
                replace_kwargs["grease_brand"] = g_brand
                replace_kwargs["grease_version"] = g_version
            if resolved_webrtc_ip is not None:
                replace_kwargs["webrtc_public_ip"] = resolved_webrtc_ip
            if replace_kwargs:
                stealth_profile = dataclasses.replace(stealth_profile, **replace_kwargs)
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
            tab = Tab(session, self, page_target["targetId"])
            tab._url = page_target.get("url", "")
            self._tabs.append(tab)
            self._main_tab = tab

            # 13. Apply stealth to initial tab session
            if stealth_engine is not None:
                await stealth_engine.apply_to_session(session)
                # T7: inject runtime stealth scripts before any navigation, so
                # stealth=True works on Chrome branded >=137 where
                # --load-extension is silently rejected.
                await stealth_engine.apply_page_scripts(session)

        # 14. Setup auto-attach for OOPIF/Worker stealth patching
        # Note: auto-attach is deferred — for stock mode the extension's
        # content-scripts handle JS injection in all frames.  Calling
        # setup_auto_attach immediately would conflict with explicit
        # Target.attachToTarget calls made by new_tab().
        # TODO: enable auto-attach selectively for OOPIF CDP patching.

        return self

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    async def new_tab(self, url: str = "about:blank") -> Tab:
        """Open a new tab, navigate to *url*, wait for load, and return it."""
        result = await self._router.root.send("Target.createTarget", {"url": "about:blank"})
        target_id = result["targetId"]
        session = await self._router.attach(target_id)

        # Apply stealth to the new tab's session
        if self._stealth_engine is not None:
            await self._stealth_engine.apply_to_session(session)
            await self._stealth_engine.apply_page_scripts(session)

        tab = Tab(session, self, target_id)
        self._tabs.append(tab)
        if url and url != "about:blank":
            await tab.get(url)
        else:
            tab._url = url
        return tab

    @property
    def tabs(self) -> list[Tab]:
        return list(self._tabs)

    @property
    def main_tab(self) -> Tab:
        if self._main_tab is None:
            raise RuntimeError("No main tab — browser may not be launched")
        return self._main_tab

    async def get(self, url: str, **kwargs: Any) -> Tab:
        """Navigate the main tab to *url* and return it."""
        tab = self.main_tab
        await tab.get(url, **kwargs)
        return tab

    # ------------------------------------------------------------------
    # Cookies
    # ------------------------------------------------------------------

    async def get_cookies(self, domain: str | None = None) -> list[Cookie]:
        """Retrieve browser cookies (optionally filtered by *domain*)."""
        result = await self._router.root.send("Storage.getCookies", {})
        cookies = [Cookie.from_json(c) for c in result.get("cookies", [])]
        if domain:
            cookies = [c for c in cookies if domain in c.domain]
        return cookies

    async def set_cookies(self, cookies: list[Cookie]) -> None:
        """Set cookies in the browser."""
        await self._router.root.send(
            "Storage.setCookies", {"cookies": [c.to_json() for c in cookies]}
        )

    async def clear_cookies(self, domain: str | None = None) -> None:
        """Clear cookies.  If *domain* is given, only clear matching cookies."""
        if domain:
            cookies = await self.get_cookies(domain)
            for c in cookies:
                await self._router.root.send("Network.deleteCookies", {
                    "name": c.name, "domain": c.domain, "path": c.path,
                })
        else:
            await self._router.root.send("Network.clearBrowserCookies", {})

    async def save_cookies(self, path: str, format: str = "json",
                           domain: str | None = None) -> None:
        """Save cookies to *path* in the given format."""
        cookies = await self.get_cookies(domain)
        Cookie.save_list(cookies, path, format=format)

    async def load_cookies(self, path: str, format: str | None = None) -> None:
        """Load cookies from *path* and set them in the browser."""
        cookies = Cookie.load_list(path, format=format)
        await self.set_cookies(cookies)

    # ------------------------------------------------------------------
    # Contexts
    # ------------------------------------------------------------------

    async def new_context(self, proxy: str | None = None) -> BrowserContext:
        """Create an isolated browser context (like incognito)."""
        params: dict[str, Any] = {}
        if proxy:
            params["proxyServer"] = proxy
        result = await self._router.root.send("Target.createBrowserContext", params)
        return BrowserContext(self, result["browserContextId"])

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Terminate the browser process and clean up resources."""
        # Cancel dispatch loop
        if self._dispatch_task and not self._dispatch_task.done():
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except (asyncio.CancelledError, Exception):
                pass

        # Close transport
        if self._router:
            try:
                await self._router._transport.close()
            except Exception:
                pass

        # Terminate Chrome
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                    self._process.wait(timeout=3)
                except Exception:
                    pass

        # Stop proxy forwarder
        if self._forwarder:
            await self._forwarder.stop()

        # Clean up temp dir
        if self._tmp_dir:
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    async def __aenter__(self) -> Browser:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

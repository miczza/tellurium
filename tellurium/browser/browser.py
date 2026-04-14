"""Browser — launch and manage a Chromium process via CDP pipes."""
from __future__ import annotations

import asyncio
import logging
import shutil
import signal
import tempfile
from pathlib import Path
from typing import Any

from tellurium.browser.cookie import Cookie
from tellurium.browser.context import BrowserContext
from tellurium.browser.engine import StockEngine, PatchedEngine
from tellurium.browser.launcher import build_chrome_flags, launch_chrome_posix
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
        """
        self = cls()

        # 1. Select engine
        if browser == "patched":
            engine = PatchedEngine(executable=executable)
        else:
            engine = StockEngine(executable=executable)

        # 2. Get executable
        chrome_path = await engine.get_executable()

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

        # 4. User-data dir
        if user_data_dir:
            self._user_data_dir = user_data_dir
        else:
            self._tmp_dir = tempfile.mkdtemp(prefix="tellurium_")
            self._user_data_dir = self._tmp_dir

        # 5. Build engine-specific args
        profile_obj = None
        if seed is not None:
            # Minimal object with .seed for PatchedEngine.build_args
            class _P:
                pass
            profile_obj = _P()
            profile_obj.seed = seed  # type: ignore[attr-defined]
        engine_args = engine.build_args(profile_obj)

        # 6. Build flags
        flags = build_chrome_flags(
            headless=headless,
            user_data_dir=self._user_data_dir,
            proxy=proxy_flag,
            extra_args=args,
            engine_args=engine_args,
        )

        # 7. Launch Chrome
        process, write_fd, read_fd = launch_chrome_posix(chrome_path, flags)
        self._process = process

        # 8. Transport + router
        transport = create_transport(read_fd, write_fd)
        await transport.start()
        self._router = SessionRouter(transport)
        self._dispatch_task = asyncio.create_task(self._router.run())

        # 9. Discover initial page target
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

        return self

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    async def new_tab(self, url: str = "about:blank") -> Tab:
        """Open a new tab and return it."""
        result = await self._router.root.send("Target.createTarget", {"url": url})
        target_id = result["targetId"]
        session = await self._router.attach(target_id)
        tab = Tab(session, self, target_id)
        tab._url = url
        self._tabs.append(tab)
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

"""BrowserContext — isolated browser context (incognito-like) backed by CDP."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from tellurium.browser.cookie import Cookie, clear_jar, read_jar

if TYPE_CHECKING:
    from tellurium.browser.browser import Browser
    from tellurium.browser.tab import Tab


class BrowserContext:
    """An isolated browser context created via ``Target.createBrowserContext``.

    Each context has its own cookie jar, local storage, cache and downloads
    folder — similar to an incognito window but programmatically controlled.
    """

    def __init__(self, browser: Browser, context_id: str, downloads_dir: Path | None = None):
        self._browser = browser
        self._context_id = context_id
        self._downloads_dir = downloads_dir
        self._tabs: list[Tab] = []

    @classmethod
    async def create(
        cls, browser: Browser, proxy: str | None = None, downloads_dir: str | Path | None = None
    ) -> BrowserContext:
        """Create a context in *browser*, with its downloads folder.

        Without *downloads_dir* the folder is a subfolder of the browser's,
        removed with the context when the browser's folder is temporary.
        """
        root = browser._router.root
        params: dict[str, Any] = {"proxyServer": proxy} if proxy else {}
        result = await root.send("Target.createBrowserContext", params)
        context = cls(browser, result["browserContextId"])
        browser._contexts[context.context_id] = context
        try:
            context._downloads_dir = await browser._downloads.add_context(
                context.context_id, downloads_dir
            )
        except BaseException:
            await context.close()
            raise
        return context

    @property
    def context_id(self) -> str:
        return self._context_id

    @property
    def downloads_dir(self) -> Path | None:
        """The folder where this context's downloads are saved."""
        return self._downloads_dir

    @property
    def tabs(self) -> list[Tab]:
        return list(self._tabs)

    async def new_tab(self, url: str = "about:blank") -> Tab:
        """Create a new tab inside this browser context.

        Like :meth:`Browser.new_tab`, the page is created blank and patched
        (stealth, overrides) before navigating to *url*.
        """
        root = self._browser._router.root
        result = await root.send(
            "Target.createTarget",
            {
                "url": "about:blank",
                "browserContextId": self._context_id,
            },
        )
        tab = await self._browser._wait_adopted(result["targetId"])
        if url and url != "about:blank":
            await tab.get(url)
        return tab

    async def get_cookies(self, domain: str | None = None) -> list[Cookie]:
        """This context's cookies; with *domain*, as :meth:`Browser.get_cookies`."""
        return await read_jar(self._browser._router.root, domain, self._context_id)

    async def clear_cookies(self, domain: str | None = None) -> None:
        """Delete this context's cookies, or only *domain*'s (and its subdomains')."""
        await clear_jar(self._browser._router.root, domain, self._context_id)

    async def set_cookies(self, cookies: list[Cookie]) -> None:
        """Set cookies in this context."""
        root = self._browser._router.root
        await root.send(
            "Storage.setCookies",
            {
                "cookies": [c.to_json() for c in cookies],
                "browserContextId": self._context_id,
            },
        )

    async def close(self) -> None:
        """Dispose of this browser context and detach all its tabs.

        Its downloads folder is removed too when it is temporary.
        """
        for tab in list(self._tabs):
            self._browser._forget_tab(tab._target_id)
        self._browser._contexts.pop(self._context_id, None)
        root = self._browser._router.root
        try:
            await root.send("Target.disposeBrowserContext", {"browserContextId": self._context_id})
        finally:
            await self._browser._downloads.remove_context(self._context_id)

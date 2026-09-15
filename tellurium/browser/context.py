"""BrowserContext — isolated browser context (incognito-like) backed by CDP."""
from __future__ import annotations

from typing import TYPE_CHECKING

from tellurium.browser.cookie import Cookie

if TYPE_CHECKING:
    from tellurium.browser.browser import Browser
    from tellurium.browser.tab import Tab


class BrowserContext:
    """An isolated browser context created via ``Target.createBrowserContext``.

    Each context has its own cookie jar, local storage, and cache — similar
    to an incognito window but programmatically controlled.
    """

    def __init__(self, browser: Browser, context_id: str):
        self._browser = browser
        self._context_id = context_id
        self._tabs: list[Tab] = []

    @property
    def context_id(self) -> str:
        return self._context_id

    @property
    def tabs(self) -> list[Tab]:
        return list(self._tabs)

    async def new_tab(self, url: str = "about:blank") -> Tab:
        """Create a new tab inside this browser context."""
        from tellurium.browser.tab import Tab

        root = self._browser._router.root
        result = await root.send("Target.createTarget", {
            "url": url,
            "browserContextId": self._context_id,
        })
        target_id = result["targetId"]
        session = await self._browser._router.attach(target_id)
        tab = Tab(session, self._browser, target_id,
                  stealth_idle=getattr(self._browser, "_stealth_idle", False),
                  mouse_profile=getattr(self._browser, "_mouse_profile", "normal"))
        tab._url = url
        self._tabs.append(tab)
        self._browser._tabs.append(tab)
        return tab

    async def get_cookies(self, domain: str | None = None) -> list[Cookie]:
        """Get cookies scoped to this context via ``Storage.getCookies``."""
        root = self._browser._router.root
        result = await root.send("Storage.getCookies", {
            "browserContextId": self._context_id,
        })
        cookies = [Cookie.from_json(c) for c in result.get("cookies", [])]
        if domain:
            cookies = [c for c in cookies if domain in c.domain]
        return cookies

    async def set_cookies(self, cookies: list[Cookie]) -> None:
        """Set cookies in this context."""
        root = self._browser._router.root
        await root.send("Storage.setCookies", {
            "cookies": [c.to_json() for c in cookies],
            "browserContextId": self._context_id,
        })

    async def close(self) -> None:
        """Dispose of this browser context and detach all its tabs."""
        for tab in list(self._tabs):
            try:
                await self._browser._router.detach(tab._session)
            except Exception:
                pass
            if tab in self._browser._tabs:
                self._browser._tabs.remove(tab)
        self._tabs.clear()
        root = self._browser._router.root
        await root.send("Target.disposeBrowserContext", {
            "browserContextId": self._context_id,
        })

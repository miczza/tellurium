"""The cookie methods of :class:`Browser`: its default context's cookie jar."""

from __future__ import annotations

import asyncio
from typing import Any

from tellurium.browser.cookie import Cookie, clear_jar, read_jar


class CookieJar:
    """Mixin of :class:`Browser`: get, set, clear, save and load its cookies."""

    _router: Any  # the browser's SessionRouter, set by Browser.launch

    async def get_cookies(self, domain: str | None = None) -> list[Cookie]:
        """Browser cookies; with *domain*, its own, its subdomains' and the
        parent-domain cookies it receives (``.example.com`` for ``sub.example.com``)."""
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

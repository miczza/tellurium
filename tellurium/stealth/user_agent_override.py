"""The User-Agent and client hints a stealth profile shows, as CDP sets them."""

from __future__ import annotations

from typing import Any

from tellurium.stealth.profile import StealthProfile


def user_agent_override(p: StealthProfile) -> dict[str, Any]:
    """Parameters of ``Emulation.setUserAgentOverride`` for profile *p*: its
    User-Agent, ``navigator.platform`` and every client hint, high-entropy ones
    included (the same for a page and for a service or shared worker)."""
    major = p.browser_version.split(".")[0]
    grease_brand = p.grease_brand or "Not_A Brand"
    grease_version = p.grease_version or "24"
    grease_version_full = p.grease_version + ".0.0.0" if p.grease_version else "24.0.0.0"
    return {
        "userAgent": p.user_agent,
        # Empty = keep Chrome's own Accept-Language (set via --accept-lang
        # at launch). A non-empty value leaks into navigator.languages.
        "acceptLanguage": "",
        "platform": p.platform,
        "userAgentMetadata": {
            "brands": [
                {"brand": "Chromium", "version": major},
                {"brand": "Google Chrome", "version": major},
                {"brand": grease_brand, "version": grease_version},
            ],
            # Chrome fills the full version itself only without
            # --user-agent, which stealth launches with (robots.txt
            # must leave with the page's UA): give it explicitly.
            "fullVersion": p.browser_version,
            "fullVersionList": [
                {"brand": "Chromium", "version": p.browser_version},
                {"brand": "Google Chrome", "version": p.browser_version},
                {"brand": grease_brand, "version": grease_version_full},
            ],
            "platform": p.ch_ua_platform,
            "platformVersion": p.platform_version,
            "architecture": p.ch_ua_arch,
            "bitness": p.ch_ua_bitness,
            "mobile": p.ch_ua_mobile,
            "model": "",
            "wow64": False,
        },
    }
